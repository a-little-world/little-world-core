"""Lobby instance detail — snapshot metrics plus live proposal/participant breakdown."""

from __future__ import annotations

from django.utils import timezone

from video.analytics.queries import (
    build_lobby_participants,
    categorize_lobby_proposals,
    proposal_statistics_from_match_lists,
)
from video.analytics.snapshots import build_snapshot_for_lobby, lobby_instance_snapshot_to_dict
from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching
from video.random_calls import is_lobby_active, open_pending_random_call_match_q


def _user_ids_with_pending_matches(user_ids: set[int], lobby: RandomCallLobby) -> set[int]:
    if not user_ids:
        return set()

    pending_qs = RandomCallMatching.objects.filter(lobby=lobby).filter(open_pending_random_call_match_q())
    u1_pending = set(pending_qs.filter(u1_id__in=user_ids).values_list("u1_id", flat=True))
    u2_pending = set(pending_qs.filter(u2_id__in=user_ids).values_list("u2_id", flat=True))
    return u1_pending | u2_pending


def build_lobby_instance_detail(lobby: RandomCallLobby) -> dict:
    """Build lobby instance detail: snapshot (attendance always final) + live proposal breakdown."""
    now = timezone.now()
    lobby_active = is_lobby_active(lobby)

    all_lobby_users = RandomCallLobbyUser.objects.filter(lobby=lobby)
    active_lobby_users = all_lobby_users.filter(is_active=True).select_related("user", "user__profile")
    active_lobby_user_ids = set(active_lobby_users.values_list("user_id", flat=True))
    classify_active_ids = active_lobby_user_ids if lobby_active else None
    pending_match_user_ids = _user_ids_with_pending_matches(active_lobby_user_ids, lobby)

    active_users_data = []
    for lobby_user in active_lobby_users:
        user = lobby_user.user
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
                "has_pending_match": user.pk in pending_match_user_ids,
            }
        )

    all_matches = list(
        RandomCallMatching.objects.filter(lobby=lobby).select_related("u1", "u2", "u1__profile", "u2__profile")
    )

    match_proposals = categorize_lobby_proposals(
        all_matches,
        lobby=lobby,
        active_lobby_user_ids=classify_active_ids,
        as_of=now,
    )

    snapshot = build_snapshot_for_lobby(lobby, proposals=all_matches, as_of=now)
    snapshot_data = lobby_instance_snapshot_to_dict(snapshot) if snapshot is not None else None

    lobby_data = {
        "name": lobby.name,
        "uuid": str(lobby.uuid),
        "is_active": lobby_active,
        "start_time": lobby.start_time.isoformat() if lobby.start_time else None,
        "end_time": lobby.end_time.isoformat() if lobby.end_time else None,
        "active_users_count": active_lobby_users.values("user_id").distinct().count(),
        "total_users_count": all_lobby_users.values("user_id").distinct().count(),
    }

    lobby_participants = build_lobby_participants(
        all_lobby_users,
        all_matches,
        lobby,
        classify_active_ids,
        as_of=now,
    )

    return {
        "snapshot": snapshot_data,
        "lobby": lobby_data,
        "active_users": active_users_data,
        "lobby_participants": lobby_participants,
        "match_proposals": match_proposals,
        "proposal_statistics": proposal_statistics_from_match_lists(match_proposals),
    }
