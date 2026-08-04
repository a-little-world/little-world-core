"""Atomic random-call lobby queries and per-lobby aggregations"""

from __future__ import annotations

from typing import Literal

from video.models import LivekitSession, RandomCallLobby, RandomCallLobbyUser, RandomCallMatching

ProposalCategory = Literal["accepted", "expired", "rejected", "dangling", "pending"]


def classify_proposal(
    proposal: RandomCallMatching,
    *,
    active_lobby_user_ids: set[int],
    proposal_stale_threshold,
) -> ProposalCategory:
    u1_in_lobby = proposal.u1_id in active_lobby_user_ids
    u2_in_lobby = proposal.u2_id in active_lobby_user_ids

    is_expired = proposal.expired or (not proposal.is_processed and (not u1_in_lobby or not u2_in_lobby))

    is_dangling_open = (
        not proposal.accepted
        and not proposal.rejected
        and not proposal.expired
        and not proposal.completed
        and (proposal.created_at is None or proposal.created_at <= proposal_stale_threshold)
    )

    if proposal.accepted:
        return "accepted"
    if is_expired:
        return "expired"
    if proposal.rejected:
        return "rejected"
    if is_dangling_open:
        return "dangling"
    if not proposal.is_processed:
        return "pending"
    return "pending"


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
