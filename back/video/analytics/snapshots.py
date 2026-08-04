"""Per-lobby occurrence snapshots — batch primitive for random-call analytics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from django.db.models import QuerySet

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
from video.analytics.timezone import DISPLAY_TZ
from video.models import RandomCallLobby, RandomCallLobbyUser

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
class LobbyOccurrenceSnapshot:
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
    completed_calls: int

    learner_count: int
    volunteer_count: int


def lobby_display_day_date(start_time: datetime | None) -> tuple[str | None, date | None]:
    if start_time is None:
        return None, None
    local = start_time.astimezone(DISPLAY_TZ)
    return local.strftime("%A"), local.date()


def _batch_user_attendance_breakdown(lobbies: list[RandomCallLobby]) -> dict[int, dict[str, int]]:
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

    user_start_times: dict[int, list[datetime]] = defaultdict(list)
    if all_user_ids:
        for row in (
            RandomCallLobbyUser.objects.filter(user_id__in=all_user_ids)
            .select_related("lobby")
            .values("user_id", "lobby__start_time")
        ):
            start_time = row["lobby__start_time"]
            if start_time is not None:
                user_start_times[row["user_id"]].append(start_time)

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

        returning = sum(1 for user_id in users if any(t < lobby.start_time for t in user_start_times.get(user_id, [])))
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


def build_snapshots(lobby_qs: QuerySet[RandomCallLobby]) -> dict[UUID, LobbyOccurrenceSnapshot]:
    """Build snapshots for every lobby in *lobby_qs* (typically one paginated page).

    *lobby_qs* must already carry annotations from ``annotate_lobby_metrics``.
    First-time / returning counts are computed in a second pass for the materialized rows only.
    """
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
    snapshots: dict[UUID, LobbyOccurrenceSnapshot] = {}

    for lobby in lobbies:
        day, snapshot_date = lobby_display_day_date(lobby.start_time)
        att = attendance[lobby.pk]
        snapshots[lobby.uuid] = LobbyOccurrenceSnapshot(
            lobby_uuid=lobby.uuid,
            lobby_name=lobby.name or "",
            start_time=lobby.start_time,
            end_time=lobby.end_time,
            day=day,
            date=snapshot_date,
            total_users=_read_annotation(lobby, ANNOT_TOTAL_USERS),
            first_time_users=att["first_time_users"],
            returning_users=att["returning_users"],
            proposals_total=_read_annotation(lobby, ANNOT_PROPOSALS_TOTAL),
            proposals_accepted=_read_annotation(lobby, ANNOT_PROPOSALS_ACCEPTED),
            proposals_rejected=_read_annotation(lobby, ANNOT_PROPOSALS_REJECTED),
            proposals_expired=_read_annotation(lobby, ANNOT_PROPOSALS_EXPIRED),
            completed_calls=_read_annotation(lobby, ANNOT_COMPLETED_CALLS),
            learner_count=_read_annotation(lobby, ANNOT_LEARNER_COUNT),
            volunteer_count=_read_annotation(lobby, ANNOT_VOLUNTEER_COUNT),
        )

    return snapshots


def build_snapshot_for_lobby(lobby: RandomCallLobby) -> LobbyOccurrenceSnapshot | None:
    """Single-lobby convenience wrapper around ``build_snapshots``."""
    annotated = annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk))
    return build_snapshots(annotated).get(lobby.uuid)


def lobby_session_snapshot_to_dict(snapshot: LobbyOccurrenceSnapshot) -> dict:
    """Serialize a lobby session snapshot for API responses (analytics list + session detail)."""
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
        "completed_calls": snapshot.completed_calls,
        "learner_count": snapshot.learner_count,
        "volunteer_count": snapshot.volunteer_count,
    }
