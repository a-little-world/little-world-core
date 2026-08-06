"""Per-lobby instance snapshots — batch primitive for random-call analytics."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from django.db.models import Min, QuerySet
from django.utils import timezone

from video.analytics.display_time import DISPLAY_TZ
from video.analytics.lobbies import (
    ANNOT_COMPLETED_CALLS,
    ANNOT_LEARNER_COUNT,
    ANNOT_PROPOSALS_ACCEPTED,
    ANNOT_PROPOSALS_EXPIRED,
    ANNOT_PROPOSALS_REJECTED,
    ANNOT_PROPOSALS_TOTAL,
    ANNOT_TOTAL_USERS,
    ANNOT_VOLUNTEER_COUNT,
    annotate_lobby_metrics,
)
from video.analytics.queries import (
    batch_count_pending_dangling_by_lobby,
    count_pending_dangling_buckets,
    proposal_bucket_mismatch,
)
from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching

logger = logging.getLogger(__name__)

_REQUIRED_ANNOTATIONS = (
    ANNOT_TOTAL_USERS,
    ANNOT_LEARNER_COUNT,
    ANNOT_VOLUNTEER_COUNT,
    ANNOT_PROPOSALS_TOTAL,
    ANNOT_PROPOSALS_ACCEPTED,
    ANNOT_PROPOSALS_REJECTED,
    ANNOT_PROPOSALS_EXPIRED,
    ANNOT_COMPLETED_CALLS,
)


@dataclass(frozen=True)
class LobbyInstanceSnapshot:
    lobby_uuid: UUID
    lobby_name: str
    start_time: datetime | None
    end_time: datetime | None
    day: str | None
    date: date | None

    total_users: int
    first_time_users: int
    returning_users: int

    proposals_total: int
    proposals_accepted: int
    proposals_rejected: int
    proposals_expired: int
    proposals_pending: int
    proposals_dangling: int
    completed_calls: int

    learner_count: int
    volunteer_count: int

    bucket_mismatch: int = 0
    proposals_are_final: bool = False


def lobby_display_day_date(start_time: datetime | None) -> tuple[str | None, date | None]:
    if start_time is None:
        return None, None
    local = start_time.astimezone(DISPLAY_TZ)
    return local.strftime("%A"), local.date()


def _batch_user_attendance_breakdown(lobbies: list[RandomCallLobby]) -> dict[int, dict[str, int]]:
    """First-time vs returning per lobby.

    Returning means the user attended any prior lobby instance (any lobby name)
    with an earlier ``start_time`` — consistent with ``compute_user_attendance_breakdown``.
    """
    if not lobbies:
        return {}

    lobby_ids = [lobby.pk for lobby in lobbies]
    participants_by_lobby: dict[int, set[int]] = defaultdict(set)
    all_user_ids: set[int] = set()

    for lobby_id, user_id in RandomCallLobbyUser.objects.filter(lobby_id__in=lobby_ids).values_list(
        "lobby_id", "user_id"
    ):
        participants_by_lobby[lobby_id].add(user_id)
        all_user_ids.add(user_id)

    user_first_seen: dict[int, datetime] = {}
    if all_user_ids:
        for row in (
            RandomCallLobbyUser.objects.filter(user_id__in=all_user_ids)
            .values("user_id")
            .annotate(first_seen=Min("lobby__start_time"))
        ):
            if row["first_seen"] is not None:
                user_first_seen[row["user_id"]] = row["first_seen"]

    breakdown: dict[int, dict[str, int]] = {}
    for lobby in lobbies:
        users = participants_by_lobby.get(lobby.pk, set())
        total = len(users)
        if total == 0:
            breakdown[lobby.pk] = {"first_time_users": 0, "returning_users": 0}
            continue
        if lobby.start_time is None:
            breakdown[lobby.pk] = {"first_time_users": total, "returning_users": 0}
            continue

        returning = sum(
            1 for user_id in users if user_id in user_first_seen and user_first_seen[user_id] < lobby.start_time
        )
        breakdown[lobby.pk] = {
            "first_time_users": total - returning,
            "returning_users": returning,
        }
    return breakdown


def _read_annotation(lobby: RandomCallLobby, name: str) -> int:
    if not hasattr(lobby, name):
        raise ValueError(
            f"Lobby queryset must be annotated before build_snapshots(); missing '{name}'. "
            "Call annotate_lobby_metrics() first."
        )
    return int(getattr(lobby, name))


def assert_sql_python_proposal_buckets_strict(
    lobby: RandomCallLobby,
    *,
    open_buckets: dict[str, int],
) -> None:
    """Hard invariant for tests and future materialization jobs — not used on GET."""
    accepted = _read_annotation(lobby, ANNOT_PROPOSALS_ACCEPTED)
    rejected = _read_annotation(lobby, ANNOT_PROPOSALS_REJECTED)
    expired = _read_annotation(lobby, ANNOT_PROPOSALS_EXPIRED)
    total = _read_annotation(lobby, ANNOT_PROPOSALS_TOTAL)
    pending = open_buckets["pending"]
    dangling = open_buckets["dangling"]
    mismatch = proposal_bucket_mismatch(
        sql_accepted=accepted,
        sql_rejected=rejected,
        sql_expired=expired,
        sql_total=total,
        pending=pending,
        dangling=dangling,
    )
    if mismatch != 0:
        raise ValueError(
            f"SQL/Python proposal bucket invariant failed for lobby {lobby.uuid}: "
            f"sql_accepted={accepted}, sql_rejected={rejected}, sql_expired={expired}, "
            f"pending={pending}, dangling={dangling}, total={total}, mismatch={mismatch}"
        )


def _merge_proposal_buckets(lobby: RandomCallLobby, *, open_buckets: dict[str, int]) -> tuple[dict[str, int], int]:
    accepted = _read_annotation(lobby, ANNOT_PROPOSALS_ACCEPTED)
    rejected = _read_annotation(lobby, ANNOT_PROPOSALS_REJECTED)
    expired = _read_annotation(lobby, ANNOT_PROPOSALS_EXPIRED)
    total = _read_annotation(lobby, ANNOT_PROPOSALS_TOTAL)
    pending = open_buckets["pending"]
    dangling = open_buckets["dangling"]
    mismatch = proposal_bucket_mismatch(
        sql_accepted=accepted,
        sql_rejected=rejected,
        sql_expired=expired,
        sql_total=total,
        pending=pending,
        dangling=dangling,
    )

    buckets = {
        "accepted": accepted,
        "rejected": rejected,
        "expired": expired,
        "pending": pending,
        "dangling": dangling,
        "total": total,
    }
    return buckets, mismatch


def _snapshot_from_lobby_row(
    lobby: RandomCallLobby,
    *,
    attendance: dict[str, int],
    open_buckets: dict[str, int],
    as_of: datetime,
) -> LobbyInstanceSnapshot:
    buckets, mismatch = _merge_proposal_buckets(lobby, open_buckets=open_buckets)

    day, snapshot_date = lobby_display_day_date(lobby.start_time)
    proposals_are_final = lobby.end_time is not None and lobby.end_time < as_of
    return LobbyInstanceSnapshot(
        lobby_uuid=lobby.uuid,
        lobby_name=lobby.name or "",
        start_time=lobby.start_time,
        end_time=lobby.end_time,
        day=day,
        date=snapshot_date,
        total_users=_read_annotation(lobby, ANNOT_TOTAL_USERS),
        first_time_users=attendance["first_time_users"],
        returning_users=attendance["returning_users"],
        proposals_total=buckets["total"],
        proposals_accepted=buckets["accepted"],
        proposals_rejected=buckets["rejected"],
        proposals_expired=buckets["expired"],
        proposals_pending=buckets["pending"],
        proposals_dangling=buckets["dangling"],
        completed_calls=_read_annotation(lobby, ANNOT_COMPLETED_CALLS),
        learner_count=_read_annotation(lobby, ANNOT_LEARNER_COUNT),
        volunteer_count=_read_annotation(lobby, ANNOT_VOLUNTEER_COUNT),
        bucket_mismatch=mismatch,
        proposals_are_final=proposals_are_final,
    )


def build_snapshots(
    lobby_qs: QuerySet[RandomCallLobby],
    *,
    as_of: datetime | None = None,
) -> dict[UUID, LobbyInstanceSnapshot]:
    """Build snapshots for every lobby in *lobby_qs* (typically one paginated page).

    Persisted-truth only: SQL accepted/rejected/expired/total plus Python pending/dangling
    with no live-user heuristics.
    """
    as_of = as_of or timezone.now()
    lobbies = list(lobby_qs)
    if not lobbies:
        return {}

    for name in _REQUIRED_ANNOTATIONS:
        if not hasattr(lobbies[0], name):
            raise ValueError(
                f"Lobby queryset must be annotated before build_snapshots(); missing '{name}'. "
                "Call annotate_lobby_metrics() first."
            )

    attendance = _batch_user_attendance_breakdown(lobbies)
    open_buckets_by_lobby = batch_count_pending_dangling_by_lobby(lobbies, as_of=as_of)
    snapshots: dict[UUID, LobbyInstanceSnapshot] = {}
    mismatched_uuids: list[str] = []

    for lobby in lobbies:
        att = attendance[lobby.pk]
        open_buckets = open_buckets_by_lobby[lobby.pk]
        snapshot = _snapshot_from_lobby_row(lobby, attendance=att, open_buckets=open_buckets, as_of=as_of)
        snapshots[lobby.uuid] = snapshot
        if snapshot.bucket_mismatch != 0:
            mismatched_uuids.append(str(lobby.uuid))

    if mismatched_uuids:
        logger.info(
            "Proposal bucket mismatch for %s lobby instance(s): %s",
            len(mismatched_uuids),
            ", ".join(mismatched_uuids),
        )

    return snapshots


def build_snapshot_for_lobby(
    lobby: RandomCallLobby,
    *,
    proposals: list[RandomCallMatching] | None = None,
    as_of: datetime | None = None,
) -> LobbyInstanceSnapshot | None:
    """Single-lobby persisted snapshot (SQL buckets + Python pending/dangling only)."""
    as_of = as_of or timezone.now()
    annotated = annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk))
    lobby_row = annotated.first()
    if lobby_row is None:
        return None

    if proposals is None:
        proposals = list(RandomCallMatching.objects.filter(lobby=lobby))

    open_buckets = count_pending_dangling_buckets(proposals, lobby=lobby, as_of=as_of)
    attendance = _batch_user_attendance_breakdown([lobby_row])[lobby_row.pk]
    snapshot = _snapshot_from_lobby_row(lobby_row, attendance=attendance, open_buckets=open_buckets, as_of=as_of)
    if snapshot.bucket_mismatch != 0:
        logger.info(
            "Proposal bucket mismatch for lobby instance %s",
            lobby_row.uuid,
        )
    return snapshot


def lobby_instance_snapshot_to_dict(snapshot: LobbyInstanceSnapshot) -> dict:
    """Serialize a lobby instance snapshot for API responses (analytics list + instance detail)."""
    return {
        "lobby_uuid": str(snapshot.lobby_uuid),
        "lobby_name": snapshot.lobby_name,
        "start_time": snapshot.start_time.isoformat() if snapshot.start_time else None,
        "end_time": snapshot.end_time.isoformat() if snapshot.end_time else None,
        "day": snapshot.day,
        "date": snapshot.date.isoformat() if snapshot.date else None,
        "total_users": snapshot.total_users,
        "first_time_users": snapshot.first_time_users,
        "returning_users": snapshot.returning_users,
        "proposals_total": snapshot.proposals_total,
        "proposals_accepted": snapshot.proposals_accepted,
        "proposals_rejected": snapshot.proposals_rejected,
        "proposals_expired": snapshot.proposals_expired,
        "proposals_pending": snapshot.proposals_pending,
        "proposals_dangling": snapshot.proposals_dangling,
        "completed_calls": snapshot.completed_calls,
        "learner_count": snapshot.learner_count,
        "volunteer_count": snapshot.volunteer_count,
        "bucket_mismatch": snapshot.bucket_mismatch,
        "proposals_are_final": snapshot.proposals_are_final,
    }
