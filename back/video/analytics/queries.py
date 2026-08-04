"""Atomic random-call lobby queries and per-lobby aggregations"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

from django.db.models import Q
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
    """Mutually exclusive expired bucket (status-first, boolean fallback for admin clears)."""
    return open_proposal_q() & (
        Q(expired=True) | Q(u1_status__in=_TERMINAL_EXPIRED_STATUSES) | Q(u2_status__in=_TERMINAL_EXPIRED_STATUSES)
    )


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
    if proposal.accepted:
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
    if proposal.accepted or _proposal_is_expired_bucket(proposal, active_lobby_user_ids=None):
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
    if _proposal_is_expired_bucket(proposal, active_lobby_user_ids=active_lobby_user_ids):
        return "expired"
    if _proposal_is_rejected_bucket(proposal):
        return "rejected"
    if _proposal_is_dangling(proposal, proposal_stale_threshold=proposal_stale_threshold):
        return "dangling"
    return "pending"


def classify_proposal(
    proposal: RandomCallMatching,
    *,
    active_lobby_user_ids: set[int],
    proposal_stale_threshold,
) -> ProposalCategory:
    """Classify a proposal for live session views (always passes active user context)."""
    return classify_proposal_bucket(
        proposal,
        active_lobby_user_ids=active_lobby_user_ids,
        proposal_stale_threshold=proposal_stale_threshold,
    )


def count_proposal_buckets(
    proposals,
    *,
    lobby: RandomCallLobby,
    active_lobby_user_ids: set[int] | None = None,
    as_of: datetime | None = None,
) -> dict[str, int]:
    stale_threshold = proposal_stale_threshold_for_lobby(lobby, as_of=as_of)
    counts = {bucket: 0 for bucket in PROPOSAL_BUCKET_FIELDS}
    for proposal in proposals:
        bucket = classify_proposal_bucket(
            proposal,
            active_lobby_user_ids=active_lobby_user_ids,
            proposal_stale_threshold=stale_threshold,
        )
        counts[bucket] += 1
    counts["total"] = len(proposals)
    return counts


def batch_count_proposal_buckets_by_lobby(
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
        lobby.pk: count_proposal_buckets(
            proposals_by_lobby.get(lobby.pk, []),
            lobby=lobby,
            as_of=as_of,
        )
        for lobby in lobbies
    }


def proposal_bucket_counts_sum_to_total(counts: dict[str, int]) -> bool:
    return sum(counts[bucket] for bucket in PROPOSAL_BUCKET_FIELDS) == counts["total"]


def serialize_lobby_participant_profile(profile):
    return {
        "first_name": profile.first_name,
        "image_type": profile.image_type,
        "avatar_config": profile.avatar_config,
        "image": profile.image.url if profile.image else None,
    }


def build_completed_call_durations(completed_proposals):
    if not completed_proposals:
        return {}

    user_ids = set()
    for proposal in completed_proposals:
        user_ids.add(proposal.u1_id)
        user_ids.add(proposal.u2_id)

    sessions = LivekitSession.objects.filter(
        random_call_session=True,
        both_have_been_active=True,
        u1_id__in=user_ids,
        u2_id__in=user_ids,
        end_time__isnull=False,
    )

    pair_durations = {}
    for session in sessions:
        pair_key = (min(session.u1_id, session.u2_id), max(session.u1_id, session.u2_id))
        duration = int((session.end_time - session.created_at).total_seconds())
        pair_durations[pair_key] = max(pair_durations.get(pair_key, 0), duration)

    proposal_durations = {}
    for proposal in completed_proposals:
        pair_key = (min(proposal.u1_id, proposal.u2_id), max(proposal.u1_id, proposal.u2_id))
        proposal_durations[proposal.pk] = pair_durations.get(pair_key, 0)

    return proposal_durations


def build_lobby_participants(all_lobby_users, all_proposals, active_lobby_user_ids, proposal_stale_threshold):
    participants = {}
    for lobby_user in all_lobby_users.select_related("user", "user__profile"):
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

    completed_proposals = [proposal for proposal in all_proposals if proposal.completed]
    proposal_durations = build_completed_call_durations(completed_proposals)

    for proposal in all_proposals:
        category = classify_proposal(
            proposal,
            active_lobby_user_ids=active_lobby_user_ids,
            proposal_stale_threshold=proposal_stale_threshold,
        )

        for user in (proposal.u1, proposal.u2):
            if user.pk not in participants:
                continue

            if category == "accepted":
                participants[user.pk]["accepted_proposals"] += 1
                if proposal.completed:
                    participants[user.pk]["completed_calls"] += 1
                    duration = proposal_durations.get(proposal.pk, 0)
                    participants[user.pk]["longest_call_duration_seconds"] = max(
                        participants[user.pk]["longest_call_duration_seconds"],
                        duration,
                    )
            elif category in ("rejected", "expired"):
                participants[user.pk]["unsuccessful_proposals"] += 1

    return sorted(participants.values(), key=lambda participant: participant["user_name"].lower())


def compute_user_attendance_breakdown(all_lobby_users, lobby: RandomCallLobby):
    participant_user_ids = list(all_lobby_users.values_list("user_id", flat=True))
    total = len(participant_user_ids)

    if total == 0:
        return {"first_time_count": 0, "returning_count": 0}

    if lobby.start_time is None:
        return {"first_time_count": total, "returning_count": 0}

    returning_user_ids = set(
        RandomCallLobbyUser.objects.filter(
            user_id__in=participant_user_ids,
            lobby__start_time__lt=lobby.start_time,
        ).values_list("user_id", flat=True)
    )
    returning_count = len(returning_user_ids)
    return {
        "first_time_count": total - returning_count,
        "returning_count": returning_count,
    }
