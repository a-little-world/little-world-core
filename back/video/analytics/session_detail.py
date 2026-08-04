"""Lobby session detail - snapshot metrics plus live proposal/participant breakdown."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from video.analytics.queries import build_lobby_participants, classify_proposal
from video.analytics.snapshots import LobbyOccurrenceSnapshot, build_snapshot_for_lobby, lobby_session_snapshot_to_dict
from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching
from video.random_calls import get_pending_random_call_matching_qs_for_user, is_lobby_active


def resolve_lobby_session(lobby_name: str, lobby_uuid=None) -> RandomCallLobby | None:
    """
    Resolve the lobby for session detail.
    - If lobby_uuid is provided, return that exact lobby instance.
    - Else, return the active lobby for lobby_name, or the most recent finished one.
    """
    if lobby_uuid:
        return RandomCallLobby.objects.get(uuid=lobby_uuid)

    now = timezone.now()
    lobby = (
        RandomCallLobby.objects.filter(
            name=lobby_name,
            start_time__lte=now,
            end_time__gte=now,
        )
        .order_by("-id")
        .first()
    )
    if lobby is None:
        lobby = (
            RandomCallLobby.objects.filter(
                name=lobby_name,
                end_time__lt=now,
            )
            .order_by("-end_time")
            .first()
        )
    return lobby


def build_lobby_session_detail(lobby: RandomCallLobby) -> dict:
    """Build session detail payload: analytics snapshot + live proposal/participant data."""
    now = timezone.now()
    lobby_active = is_lobby_active(lobby)

    all_lobby_users = RandomCallLobbyUser.objects.filter(lobby=lobby)
    active_lobby_users = all_lobby_users.filter(is_active=True)

    active_users_data = []
    for lobby_user in active_lobby_users:
        user = lobby_user.user
        has_pending_match = get_pending_random_call_matching_qs_for_user(user, lobby).exists()
        active_users_data.append(
            {
                "uuid": str(lobby_user.uuid),
                "user_uuid": str(user.uuid),
                "user_name": f"{user.profile.first_name}",
                "user_type": user.profile.user_type,
                "is_active": lobby_user.is_active,
                "last_status_checked_at": lobby_user.last_status_checked_at.isoformat()
                if lobby_user.last_status_checked_at
                else None,
                "has_pending_match": has_pending_match,
            }
        )

    all_matches = RandomCallMatching.objects.filter(lobby=lobby).select_related("u1", "u2")

    pending_matches = []
    accepted_matches = []
    rejected_matches = []
    expired_matches = []
    dangling_matches = []

    proposal_stale_threshold = now - timedelta(seconds=lobby.match_proposal_timeout)
    active_lobby_user_ids = set(active_lobby_users.values_list("user_id", flat=True))

    for match in all_matches:
        match_data = {
            "uuid": str(match.uuid),
            "u1_uuid": str(match.u1.uuid),
            "u1_name": f"{match.u1.profile.first_name}",
            "u1_user_type": match.u1.profile.user_type,
            "u2_uuid": str(match.u2.uuid),
            "u2_name": f"{match.u2.profile.first_name}",
            "u2_user_type": match.u2.profile.user_type,
            "u1_accepted": match.u1_accepted,
            "u2_accepted": match.u2_accepted,
            "u1_status": match.u1_status,
            "u2_status": match.u2_status,
            "accepted": match.accepted,
            "rejected": match.rejected,
            "expired": match.expired,
            "completed": match.completed,
            "in_session": match.in_session,
            "created_at": match.created_at,
        }

        category = classify_proposal(
            match,
            active_lobby_user_ids=active_lobby_user_ids,
            proposal_stale_threshold=proposal_stale_threshold,
        )

        if category == "accepted":
            accepted_matches.append(match_data)
        elif category == "expired":
            expired_matches.append(match_data)
        elif category == "rejected":
            rejected_matches.append(match_data)
        elif category == "dangling":
            dangling_matches.append(match_data)
        elif category == "pending":
            pending_matches.append(match_data)

    snapshot: LobbyOccurrenceSnapshot | None = build_snapshot_for_lobby(lobby)

    lobby_data = {
        "name": lobby.name,
        "uuid": str(lobby.uuid),
        "is_active": lobby_active,
        "start_time": lobby.start_time.isoformat() if lobby.start_time else None,
        "end_time": lobby.end_time.isoformat() if lobby.end_time else None,
        "active_users_count": active_lobby_users.count(),
        "total_users_count": all_lobby_users.count(),
    }

    lobby_participants = build_lobby_participants(
        all_lobby_users,
        all_matches,
        active_lobby_user_ids,
        proposal_stale_threshold,
    )

    return {
        "snapshot": lobby_session_snapshot_to_dict(snapshot) if snapshot else None,
        "lobby": lobby_data,
        "active_users": active_users_data,
        "lobby_participants": lobby_participants,
        "match_proposals": {
            "pending": pending_matches,
            "accepted": accepted_matches,
            "rejected": rejected_matches,
            "expired": expired_matches,
            "dangling": dangling_matches,
        },
        "proposal_statistics": {
            "total_matches": all_matches.count(),
            "pending_count": len(pending_matches),
            "accepted_count": len(accepted_matches),
            "rejected_count": len(rejected_matches),
            "expired_count": len(expired_matches),
            "dangling_count": len(dangling_matches),
        },
    }
