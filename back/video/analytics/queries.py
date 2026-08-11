"""Atomic random-call lobby queries and per-lobby aggregations"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

from django.db.models import Min, Q
from django.utils import timezone

from video.models import (
    LivekitSession,
    RandomCallLobby,
    RandomCallLobbyUser,
    RandomCallMatching,
    RandomCallProposalUserStatus,
)

ProposalCategory = Literal["accepted", "expired", "rejected", "dangling", "pending"]

PROPOSAL_BUCKET_FIELDS = ("accepted", "rejected", "expired", "pending", "dangling")

_TERMINAL_EXPIRED_STATUSES = (
    RandomCallProposalUserStatus.EXPIRED,
    RandomCallProposalUserStatus.EXITED,
)


def open_proposal_q() -> Q:
    return Q(accepted=False, completed=False)


def expired_proposal_bucket_q() -> Q:
    """Mutually exclusive expired bucket (status-first, boolean fallback for admin clears).

    legacy_orphan: pre-2026-08-04 rows marked completed without accept (unscoped webhook).
    No new rows of this shape after webhook scoping shipped — delete this branch once backfilled.
    """
    legacy_orphan = Q(accepted=False, completed=True)
    open_expired = open_proposal_q() & (
        Q(expired=True) | Q(u1_status__in=_TERMINAL_EXPIRED_STATUSES) | Q(u2_status__in=_TERMINAL_EXPIRED_STATUSES)
    )
    return legacy_orphan | open_expired


def rejected_proposal_bucket_q() -> Q:
    """Mutually exclusive rejected bucket — excludes expired-bucket rows (e.g. timeouts)."""
    not_expired = (
        ~Q(expired=True) & ~Q(u1_status__in=_TERMINAL_EXPIRED_STATUSES) & ~Q(u2_status__in=_TERMINAL_EXPIRED_STATUSES)
    )
    return (
        open_proposal_q()
        & not_expired
        & (
            Q(u1_status=RandomCallProposalUserStatus.REJECTED)
            | Q(u2_status=RandomCallProposalUserStatus.REJECTED)
            | Q(rejected=True, rejected_at__isnull=False)
        )
    )


def accepted_proposal_bucket_q() -> Q:
    return Q(accepted=True)


def proposal_stale_threshold_for_lobby(lobby: RandomCallLobby, *, as_of: datetime | None = None) -> datetime:
    """Reference time for dangling: lobby end if finished, otherwise now."""
    as_of = as_of or timezone.now()
    reference = as_of
    if lobby.end_time is not None and lobby.end_time < as_of:
        reference = lobby.end_time
    return reference - timedelta(seconds=lobby.match_proposal_timeout)


def _proposal_is_expired_bucket(
    proposal: RandomCallMatching,
    *,
    active_lobby_user_ids: set[int] | None,
) -> bool:
    if proposal.accepted or proposal.completed:
        return False
    if proposal.expired:
        return True
    if proposal.u1_status in _TERMINAL_EXPIRED_STATUSES or proposal.u2_status in _TERMINAL_EXPIRED_STATUSES:
        return True
    if active_lobby_user_ids is not None and not proposal.is_processed:
        u1_in_lobby = proposal.u1_id in active_lobby_user_ids
        u2_in_lobby = proposal.u2_id in active_lobby_user_ids
        if not u1_in_lobby or not u2_in_lobby:
            return True
    return False


def _proposal_is_rejected_bucket(proposal: RandomCallMatching) -> bool:
    if proposal.accepted or proposal.completed:
        return False
    if _proposal_is_expired_bucket(proposal, active_lobby_user_ids=None):
        return False
    if (
        proposal.u1_status == RandomCallProposalUserStatus.REJECTED
        or proposal.u2_status == RandomCallProposalUserStatus.REJECTED
    ):
        return True
    return bool(proposal.rejected and proposal.rejected_at is not None)


def _proposal_is_dangling(proposal: RandomCallMatching, *, proposal_stale_threshold: datetime) -> bool:
    if proposal.accepted or proposal.completed:
        return False
    if _proposal_is_expired_bucket(proposal, active_lobby_user_ids=None):
        return False
    if _proposal_is_rejected_bucket(proposal):
        return False
    return proposal.created_at is None or proposal.created_at <= proposal_stale_threshold


def classify_proposal_bucket(
    proposal: RandomCallMatching,
    *,
    active_lobby_user_ids: set[int] | None = None,
    proposal_stale_threshold: datetime,
) -> ProposalCategory:
    """Assign each proposal to exactly one mutually exclusive bucket."""
    if proposal.accepted:
        return "accepted"
    if proposal.completed and not proposal.accepted:
        return "expired"
    if _proposal_is_expired_bucket(proposal, active_lobby_user_ids=active_lobby_user_ids):
        return "expired"
    if _proposal_is_rejected_bucket(proposal):
        return "rejected"
    if _proposal_is_dangling(proposal, proposal_stale_threshold=proposal_stale_threshold):
        return "dangling"
    return "pending"


def count_pending_dangling_buckets(
    proposals,
    *,
    lobby: RandomCallLobby,
    as_of: datetime | None = None,
) -> dict[str, int]:
    """Classify only open, non-accepted proposals into pending/dangling (SQL owns the other buckets)."""
    stale_threshold = proposal_stale_threshold_for_lobby(lobby, as_of=as_of)
    counts = {"pending": 0, "dangling": 0}
    for proposal in proposals:
        if proposal.accepted or proposal.completed:
            continue
        bucket = classify_proposal_bucket(
            proposal,
            active_lobby_user_ids=None,
            proposal_stale_threshold=stale_threshold,
        )
        if bucket in counts:
            counts[bucket] += 1
    return counts


def batch_count_pending_dangling_by_lobby(
    lobbies: list[RandomCallLobby],
    *,
    as_of: datetime | None = None,
) -> dict[int, dict[str, int]]:
    if not lobbies:
        return {}

    lobby_ids = [lobby.pk for lobby in lobbies]
    proposals_by_lobby: dict[int, list[RandomCallMatching]] = defaultdict(list)
    for proposal in RandomCallMatching.objects.filter(lobby_id__in=lobby_ids):
        proposals_by_lobby[proposal.lobby_id].append(proposal)

    return {
        lobby.pk: count_pending_dangling_buckets(
            proposals_by_lobby.get(lobby.pk, []),
            lobby=lobby,
            as_of=as_of,
        )
        for lobby in lobbies
    }


def proposal_bucket_mismatch(
    *,
    sql_accepted: int,
    sql_rejected: int,
    sql_expired: int,
    sql_total: int,
    pending: int,
    dangling: int,
) -> int:
    return sql_total - (sql_accepted + sql_rejected + sql_expired + pending + dangling)


def proposal_statistics_from_match_lists(match_proposals: dict[str, list]) -> dict[str, int]:
    """Live operational counts derived from categorized proposal lists."""
    return {
        "total_matches": sum(len(matches) for matches in match_proposals.values()),
        "pending_count": len(match_proposals["pending"]),
        "accepted_count": len(match_proposals["accepted"]),
        "rejected_count": len(match_proposals["rejected"]),
        "expired_count": len(match_proposals["expired"]),
        "dangling_count": len(match_proposals["dangling"]),
    }


def serialize_proposal_for_api(proposal: RandomCallMatching) -> dict:
    return {
        "uuid": str(proposal.uuid),
        "u1_uuid": str(proposal.u1.uuid),
        "u1_name": f"{proposal.u1.profile.first_name}",
        "u1_user_type": proposal.u1.profile.user_type,
        "u2_uuid": str(proposal.u2.uuid),
        "u2_name": f"{proposal.u2.profile.first_name}",
        "u2_user_type": proposal.u2.profile.user_type,
        "u1_accepted": proposal.u1_accepted,
        "u2_accepted": proposal.u2_accepted,
        "u1_status": proposal.u1_status,
        "u2_status": proposal.u2_status,
        "accepted": proposal.accepted,
        "rejected": proposal.rejected,
        "expired": proposal.expired,
        "completed": proposal.completed,
        "in_session": proposal.in_session,
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
    }


def categorize_lobby_proposals(
    proposals,
    *,
    lobby: RandomCallLobby,
    active_lobby_user_ids: set[int] | None = None,
    as_of: datetime | None = None,
) -> dict[str, list]:
    """Live classification for operational proposal lists (may use active-user heuristics)."""
    stale_threshold = proposal_stale_threshold_for_lobby(lobby, as_of=as_of)
    lists: dict[str, list] = {bucket: [] for bucket in PROPOSAL_BUCKET_FIELDS}

    for proposal in proposals:
        category = classify_proposal_bucket(
            proposal,
            active_lobby_user_ids=active_lobby_user_ids,
            proposal_stale_threshold=stale_threshold,
        )
        lists[category].append(serialize_proposal_for_api(proposal))

    return lists


def serialize_lobby_participant_profile(profile):
    return {
        "first_name": profile.first_name,
        "image_type": profile.image_type,
        "avatar_config": profile.avatar_config,
        "image": profile.image.url if profile.image else None,
    }


def _lobby_call_start_window(lobby: RandomCallLobby) -> tuple[datetime | None, datetime | None]:
    """Lobby bounds apply to when a call may *start*, not when it may end."""
    return lobby.start_time, lobby.end_time


def _session_duration_seconds(session) -> int:
    return int((session.end_time - session.created_at).total_seconds())


def _pair_key_for_users(u1_id: int, u2_id: int) -> tuple[int, int]:
    return (min(u1_id, u2_id), max(u1_id, u2_id))


def _proposal_accept_sort_key(proposal: RandomCallMatching):
    accepted_at = proposal.accepted_at
    if accepted_at is None:
        return (0, datetime.min.replace(tzinfo=timezone.utc), proposal.pk)
    return (1, accepted_at, proposal.pk)


def _pick_session_for_proposal(
    sessions,
    proposal: RandomCallMatching,
    lobby: RandomCallLobby,
    *,
    next_accepted_at: datetime | None = None,
):
    """Pick the LiveKit session for a completed proposal (pair + start-time window).

    Window is [accepted_at, next_same_pair_accepted_at) when the pair rematches,
    otherwise [accepted_at, lobby.end_time]. Within that window, take the longest
    session so short reconnect attempts do not hide the real call duration.
    """
    lobby_start, lobby_end = _lobby_call_start_window(lobby)
    earliest_start = proposal.accepted_at or lobby_start

    candidates = []
    for session in sessions:
        if earliest_start is not None and session.created_at < earliest_start:
            continue
        if next_accepted_at is not None:
            # Exclusive upper bound so the rematch's own session is not stolen.
            if session.created_at >= next_accepted_at:
                continue
        elif lobby_end is not None and session.created_at > lobby_end:
            continue
        candidates.append(session)

    if not candidates:
        return None

    return max(candidates, key=_session_duration_seconds)


def build_completed_call_durations(completed_proposals, *, lobby: RandomCallLobby):
    if not completed_proposals:
        return {}

    lobby_start, lobby_end = _lobby_call_start_window(lobby)
    user_ids = {proposal.u1_id for proposal in completed_proposals} | {
        proposal.u2_id for proposal in completed_proposals
    }
    expected_pairs = {_pair_key_for_users(proposal.u1_id, proposal.u2_id) for proposal in completed_proposals}

    sessions = LivekitSession.objects.filter(
        random_call_session=True,
        both_have_been_active=True,
        end_time__isnull=False,
        u1_id__in=user_ids,
        u2_id__in=user_ids,
    )
    if lobby_start is not None:
        sessions = sessions.filter(created_at__gte=lobby_start)
    if lobby_end is not None:
        sessions = sessions.filter(created_at__lte=lobby_end)

    sessions_by_pair: dict[tuple[int, int], list] = defaultdict(list)
    for session in sessions:
        pair_key = _pair_key_for_users(session.u1_id, session.u2_id)
        if pair_key in expected_pairs:
            sessions_by_pair[pair_key].append(session)

    proposals_by_pair: dict[tuple[int, int], list[RandomCallMatching]] = defaultdict(list)
    for proposal in completed_proposals:
        proposals_by_pair[_pair_key_for_users(proposal.u1_id, proposal.u2_id)].append(proposal)

    proposal_durations = {}
    for pair_key, pair_proposals in proposals_by_pair.items():
        pair_proposals.sort(key=_proposal_accept_sort_key)
        pair_sessions = sessions_by_pair.get(pair_key, [])
        for index, proposal in enumerate(pair_proposals):
            next_accepted_at = None
            if index + 1 < len(pair_proposals):
                next_accepted_at = pair_proposals[index + 1].accepted_at
            session = _pick_session_for_proposal(
                pair_sessions,
                proposal,
                lobby,
                next_accepted_at=next_accepted_at,
            )
            if session is None:
                proposal_durations[proposal.pk] = 0
                continue
            proposal_durations[proposal.pk] = _session_duration_seconds(session)

    return proposal_durations


def build_lobby_participants(all_lobby_users, all_proposals, lobby, active_lobby_user_ids, *, as_of=None):
    proposal_stale_threshold = proposal_stale_threshold_for_lobby(lobby, as_of=as_of)
    participants = {}
    for lobby_user in all_lobby_users.order_by("-id").select_related("user", "user__profile"):
        user = lobby_user.user
        participants[user.pk] = {
            "user_id": user.pk,
            "user_uuid": str(user.uuid),
            "user_name": f"{user.profile.first_name}",
            "user_type": user.profile.user_type,
            "is_active": lobby_user.is_active,
            "completed_calls": 0,
            "unsuccessful_proposals": 0,
            "accepted_proposals": 0,
            "longest_call_duration_seconds": 0,
            "profile": serialize_lobby_participant_profile(user.profile),
        }

    proposal_categories: list[tuple[RandomCallMatching, ProposalCategory]] = []
    for proposal in all_proposals:
        category = classify_proposal_bucket(
            proposal,
            active_lobby_user_ids=active_lobby_user_ids,
            proposal_stale_threshold=proposal_stale_threshold,
        )
        proposal_categories.append((proposal, category))

        for user in (proposal.u1, proposal.u2):
            if user.pk not in participants:
                continue

            if category == "accepted":
                participants[user.pk]["accepted_proposals"] += 1
            elif category in ("rejected", "expired"):
                participants[user.pk]["unsuccessful_proposals"] += 1

    accepted_completed = [
        proposal for proposal, category in proposal_categories if category == "accepted" and proposal.completed
    ]
    proposal_durations = build_completed_call_durations(accepted_completed, lobby=lobby)

    for proposal, category in proposal_categories:
        if category != "accepted" or not proposal.completed:
            continue
        duration = proposal_durations.get(proposal.pk, 0)
        for user in (proposal.u1, proposal.u2):
            if user.pk not in participants:
                continue
            participants[user.pk]["completed_calls"] += 1
            participants[user.pk]["longest_call_duration_seconds"] = max(
                participants[user.pk]["longest_call_duration_seconds"],
                duration,
            )

    return sorted(participants.values(), key=lambda participant: participant["user_name"].lower())


def compute_user_attendance_breakdown(all_lobby_users, lobby: RandomCallLobby):
    """First-time vs returning for a single lobby (any prior lobby name counts as returning)."""
    participant_user_ids = list(all_lobby_users.values_list("user_id", flat=True).distinct())
    total = len(participant_user_ids)

    if total == 0:
        return {"first_time_count": 0, "returning_count": 0}

    if lobby.start_time is None:
        return {"first_time_count": total, "returning_count": 0}

    returning_user_ids = {
        row["user_id"]
        for row in RandomCallLobbyUser.objects.filter(user_id__in=participant_user_ids)
        .values("user_id")
        .annotate(first_seen=Min("lobby__start_time"))
        if row["first_seen"] is not None and row["first_seen"] < lobby.start_time
    }
    returning_count = len(returning_user_ids)
    return {
        "first_time_count": total - returning_count,
        "returning_count": returning_count,
    }
