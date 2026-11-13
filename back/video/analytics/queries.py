"""Atomic random-call lobby queries and per-lobby aggregations"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from typing import Literal

from django.db.models import Min, Q
from django.utils import timezone
from management.models.profile import Profile

from video.models import (
    LivekitSession,
    RandomCallLobby,
    RandomCallLobbyUser,
    RandomCallMatching,
    RandomCallProposalUserStatus,
)

ProposalCategory = Literal["accepted", "expired", "rejected", "dangling", "pending"]

PROPOSAL_BUCKET_FIELDS = ("accepted", "rejected", "expired", "pending", "dangling")

ProposalPairType = Literal["learner_learner", "learner_volunteer", "other"]

PROPOSAL_PAIR_TYPES: tuple[ProposalPairType, ...] = ("learner_learner", "learner_volunteer", "other")

# Buckets that carry a pair split. The open buckets (pending, dangling) describe proposals
# nobody has answered yet, where who was paired says nothing about an outcome.
PAIR_BREAKDOWN_BUCKETS = ("accepted", "rejected", "expired")


def classify_proposal_pair(u1_user_type: str | None, u2_user_type: str | None) -> ProposalPairType:
    """Who a proposal paired, as one of ``PROPOSAL_PAIR_TYPES``.

    Mutually exclusive and exhaustive (§8): "other" absorbs volunteer-volunteer and any
    profile with no type set. The matcher should not produce either, but a row that
    matches nothing has to land somewhere visible rather than vanish from the split (§17).
    """
    types = {u1_user_type, u2_user_type}
    if types == {Profile.TypeChoices.LEARNER}:
        return "learner_learner"
    if types == {Profile.TypeChoices.LEARNER, Profile.TypeChoices.VOLUNTEER}:
        return "learner_volunteer"
    return "other"


_TERMINAL_EXPIRED_STATUSES = (
    RandomCallProposalUserStatus.EXPIRED,
    RandomCallProposalUserStatus.EXITED,
)

# A proposal both users accepted and completed is a *completed* call; it only counts as a
# *successful* one once the pair actually talked for this long. Two people connecting and
# dropping out after a few seconds is not a conversation, and counting it as one inflates
# every success rate on the page.
#
# Applied to the proposal's total duration, not to each LiveKit session: a call that drops
# and reconnects is one conversation split across rows (see `_sessions_for_proposal`), so
# 40s + 30s is a 70s call, not two failures.
MIN_SUCCESSFUL_CALL_SECONDS = 60


def is_successful_call(duration_seconds: int) -> bool:
    """Single definition of "successful call" — every count on the page routes through it."""
    return duration_seconds >= MIN_SUCCESSFUL_CALL_SECONDS


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
    """Live operational counts derived from categorized proposal lists.

    Each outcome bucket also carries a learner-learner / learner-volunteer / other split,
    counted from the very same lists as the totals above it. Deriving both from one pass is
    what stops a breakdown disagreeing with its own headline number, or with the proposal
    list rendered beneath it (§7).
    """
    stats: dict[str, int] = {
        "total_matches": sum(len(matches) for matches in match_proposals.values()),
        "pending_count": len(match_proposals["pending"]),
        "accepted_count": len(match_proposals["accepted"]),
        "rejected_count": len(match_proposals["rejected"]),
        "expired_count": len(match_proposals["expired"]),
        "dangling_count": len(match_proposals["dangling"]),
    }

    for bucket in PAIR_BREAKDOWN_BUCKETS:
        pair_counts = Counter(
            classify_proposal_pair(proposal["u1_user_type"], proposal["u2_user_type"])
            for proposal in match_proposals[bucket]
        )
        for pair_type in PROPOSAL_PAIR_TYPES:
            stats[f"{bucket}_{pair_type}_count"] = pair_counts[pair_type]

    return stats


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


#: Sort sentinel for proposals with no ``accepted_at``. Uses ``datetime.timezone.utc`` —
#: ``django.utils.timezone.utc`` was removed in Django 5.0 and raises AttributeError.
_EPOCH = datetime.min.replace(tzinfo=datetime_timezone.utc)


def _lobby_call_start_window(lobby: RandomCallLobby) -> tuple[datetime | None, datetime | None]:
    """Lobby bounds apply to when a call may *start*, not when it may end."""
    return lobby.start_time, lobby.end_time


def _session_duration_seconds(session) -> int:
    return int((session.end_time - session.created_at).total_seconds())


def _pair_key_for_users(u1_id: int, u2_id: int) -> tuple[int, int]:
    return (min(u1_id, u2_id), max(u1_id, u2_id))


def _proposal_accept_sort_key(proposal: RandomCallMatching):
    """Order a pair's proposals by acceptance time, unaccepted ones first.

    ``accepted_at`` is nullable and frequently unset even when ``accepted`` is True, so
    the key has to tolerate ``None`` — sorting a tuple whose second element is sometimes
    ``None`` and sometimes a datetime would raise.
    """
    if proposal.accepted_at is None:
        return (0, _EPOCH, proposal.pk)
    return (1, proposal.accepted_at, proposal.pk)


def _sessions_for_proposal(
    sessions,
    proposal: RandomCallMatching,
    lobby: RandomCallLobby,
    *,
    next_accepted_at: datetime | None = None,
    pair_has_other_proposals: bool = False,
) -> list:
    """Sessions belonging to one completed proposal, by pair and start-time window.

    Window is ``[accepted_at, next_same_pair_accepted_at)`` when the pair rematches within
    the lobby, otherwise ``[accepted_at, lobby.end_time]``. The half-open upper bound is
    what stops a rematch's session being attributed to the earlier proposal.

    ``accepted_at`` is NULL on every row created before migration ``video.0024``
    (2026-04-23) added the column without a backfill; the write path has always set it
    since. Those rows still get a duration when the pair has only this one proposal in the
    lobby — the lobby window identifies the call on its own, so nothing is ambiguous and
    no timestamp has to be invented. With a *second* proposal for the same pair there is
    no way to tell which call belongs to which, and guessing is how one session ended up
    counted against two proposals, so those report nothing.

    Returns *all* sessions in the window, not one: a call that drops and reconnects is one
    conversation split across rows, and the caller sums them.
    """
    lobby_start, lobby_end = _lobby_call_start_window(lobby)

    if proposal.accepted_at is None:
        if pair_has_other_proposals:
            return []
        earliest_start = lobby_start
    else:
        earliest_start = proposal.accepted_at

    windowed = []
    for session in sessions:
        if earliest_start is not None and session.created_at < earliest_start:
            continue
        if next_accepted_at is not None:
            if session.created_at >= next_accepted_at:
                continue
        elif lobby_end is not None and session.created_at > lobby_end:
            continue
        windowed.append(session)

    return windowed


def _durations_for_one_lobby(completed_proposals, *, lobby: RandomCallLobby, sessions_by_pair) -> dict[int, int]:
    """Window a lobby's pair sessions onto its proposals. Shared by both public forms."""
    proposals_by_pair: dict[tuple[int, int], list[RandomCallMatching]] = defaultdict(list)
    for proposal in completed_proposals:
        proposals_by_pair[_pair_key_for_users(proposal.u1_id, proposal.u2_id)].append(proposal)

    proposal_durations = {}
    for pair_key, pair_proposals in proposals_by_pair.items():
        pair_proposals.sort(key=_proposal_accept_sort_key)
        pair_sessions = sessions_by_pair.get(pair_key, [])
        for index, proposal in enumerate(pair_proposals):
            # Only a *later* acceptance closes this proposal's window. Unaccepted
            # proposals sort first and carry no time, so they cannot bound anything.
            next_accepted_at = None
            for later in pair_proposals[index + 1 :]:
                if later.accepted_at is not None:
                    next_accepted_at = later.accepted_at
                    break

            windowed = _sessions_for_proposal(
                pair_sessions,
                proposal,
                lobby,
                next_accepted_at=next_accepted_at,
                pair_has_other_proposals=len(pair_proposals) > 1,
            )
            # Summed, not maxed: a dropped call that reconnects is one conversation split
            # across rows, and reporting only the longest leg silently discards the rest.
            proposal_durations[proposal.pk] = sum(_session_duration_seconds(s) for s in windowed)

    return proposal_durations


def _sessions_by_pair(completed_proposals, *, start: datetime | None, end: datetime | None):
    """LiveKit sessions for the given proposals' pairs, in one query, keyed by pair.

    ``start``/``end`` only narrow what SQL fetches; the authoritative per-proposal window
    is applied by ``_sessions_for_proposal``. A ``None`` bound means unbounded, which is
    what a lobby with no ``end_time`` already produced.
    """
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
    if start is not None:
        sessions = sessions.filter(created_at__gte=start)
    if end is not None:
        sessions = sessions.filter(created_at__lte=end)

    sessions_by_pair: dict[tuple[int, int], list] = defaultdict(list)
    for session in sessions:
        pair_key = _pair_key_for_users(session.u1_id, session.u2_id)
        if pair_key in expected_pairs:
            sessions_by_pair[pair_key].append(session)
    return sessions_by_pair


def batch_completed_call_durations(
    proposals_by_lobby: dict[int, list[RandomCallMatching]],
    *,
    lobbies_by_id: dict[int, RandomCallLobby],
) -> dict[int, int]:
    """Per-proposal call duration across many lobbies, in one LiveKit query.

    The batch form is the primitive and ``build_completed_call_durations`` is the
    one-lobby call of it (§5); windowing lives in ``_sessions_for_proposal`` alone, so
    the list and detail views cannot drift on what a call's duration is.

    The SQL window spans every lobby in the batch, which is wider than any single lobby's
    — harmless, because ``_sessions_for_proposal`` re-applies each lobby's own bounds and
    a pair's sessions from a *later* lobby fall outside the earlier lobby's ``end_time``.
    """
    all_proposals = [proposal for proposals in proposals_by_lobby.values() for proposal in proposals]
    if not all_proposals:
        return {}

    starts = [lobbies_by_id[lobby_id].start_time for lobby_id in proposals_by_lobby]
    ends = [lobbies_by_id[lobby_id].end_time for lobby_id in proposals_by_lobby]
    # A single unbounded lobby makes the batch bound unbounded on that side, matching
    # what that lobby would have queried on its own.
    start = None if any(value is None for value in starts) else min(starts)
    end = None if any(value is None for value in ends) else max(ends)

    sessions_by_pair = _sessions_by_pair(all_proposals, start=start, end=end)

    durations: dict[int, int] = {}
    for lobby_id, proposals in proposals_by_lobby.items():
        durations.update(
            _durations_for_one_lobby(
                proposals,
                lobby=lobbies_by_id[lobby_id],
                sessions_by_pair=sessions_by_pair,
            )
        )
    return durations


def build_completed_call_durations(completed_proposals, *, lobby: RandomCallLobby):
    """Single-lobby call durations — a one-element ``batch_completed_call_durations``."""
    if not completed_proposals:
        return {}

    return batch_completed_call_durations({lobby.pk: list(completed_proposals)}, lobbies_by_id={lobby.pk: lobby})


def build_lobby_participants(all_lobby_users, all_proposals, lobby, active_lobby_user_ids, *, as_of=None):
    proposal_stale_threshold = proposal_stale_threshold_for_lobby(lobby, as_of=as_of)
    participants = {}
    # `-id` first, and the first row per user wins: (user, lobby) carries no unique
    # constraint, so duplicates are possible and the newest row is the one whose
    # `is_active` reflects the user's current state.
    for lobby_user in all_lobby_users.order_by("-id").select_related("user", "user__profile"):
        user = lobby_user.user
        first_joined_at = lobby_user.first_joined_at
        existing = participants.get(user.pk)
        if existing is not None:
            # Earliest join across the duplicates. Held as a datetime and serialized once
            # below — comparing ISO strings only matches time order while every value
            # carries the same UTC offset.
            earliest = existing["first_joined_at"]
            if first_joined_at is not None and (earliest is None or first_joined_at < earliest):
                existing["first_joined_at"] = first_joined_at
            continue

        participants[user.pk] = {
            "user_id": user.pk,
            "user_uuid": str(user.uuid),
            "user_name": f"{user.profile.first_name}",
            "user_type": user.profile.user_type,
            "is_active": lobby_user.is_active,
            "first_joined_at": first_joined_at,
            "completed_calls": 0,
            "successful_calls": 0,
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
            if is_successful_call(duration):
                participants[user.pk]["successful_calls"] += 1
            participants[user.pk]["longest_call_duration_seconds"] = max(
                participants[user.pk]["longest_call_duration_seconds"],
                duration,
            )

    ordered = sorted(participants.values(), key=lambda participant: participant["user_name"].lower())
    for participant in ordered:
        joined_at = participant["first_joined_at"]
        participant["first_joined_at"] = joined_at.isoformat() if joined_at else None
    return ordered


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
