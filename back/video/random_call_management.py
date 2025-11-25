from django.db.models import Q
from django.urls import path
from django.utils import timezone
from management.authentication import NativeOnlyJWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from management.helpers import IsAdminOrMatchingUser

from video.models import (
    RandomCallLobby,
    RandomCallLobbyUser,
    RandomCallMatching,
)
from video.random_calls import is_lobby_active


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def get_lobby_management_overview(request, lobby_name="default"):
    """
    Admin monitoring API to get comprehensive overview of a random call lobby.
    Returns:
    - Lobby metadata and status
    - List of active users with their status
    - Match proposals categorized by status (pending, accepted, rejected, expired)
    - Statistics summary
    """
    # 1 - Retrieve the lobby
    try:
        lobby = RandomCallLobby.objects.get(name=lobby_name)
    except RandomCallLobby.DoesNotExist:
        return Response({"error": "Lobby not found"}, status=404)

    # 2 - Check if the lobby is active
    lobby_active = is_lobby_active(lobby)

    # 3 - Get all users in the lobby (both active and inactive)
    all_lobby_users = RandomCallLobbyUser.objects.filter(lobby=lobby)
    active_lobby_users = all_lobby_users.filter(is_active=True)

    # 4 - Serialize active users with additional info
    active_users_data = []
    for lobby_user in active_lobby_users:
        user = lobby_user.user
        # Check if user has pending match
        has_pending_match = RandomCallMatching.objects.filter(
            Q(u1=user) | Q(u2=user),
            lobby=lobby,
            rejected=False,
            accepted=False
        ).exists()

        active_users_data.append({
            "uuid": str(lobby_user.uuid),
            "user_hash": user.hash,
            "user_name": f"{user.profile.first_name}",
            "is_active": lobby_user.is_active,
            "last_status_checked_at": lobby_user.last_status_checked_at.isoformat() if lobby_user.last_status_checked_at else None,
            "has_pending_match": has_pending_match,
        })

    # 5 - Get all match proposals for this lobby
    all_matches = RandomCallMatching.objects.filter(lobby=lobby).select_related('u1', 'u2')

    # 6 - Categorize matches by status
    pending_matches = []
    accepted_matches = []
    rejected_matches = []
    expired_matches = []

    for match in all_matches:
        match_data = {
            "uuid": str(match.uuid),
            "u1": {
                "hash": match.u1.hash,
                "name": f"{match.u1.profile.first_name}",
            },
            "u2": {
                "hash": match.u2.hash,
                "name": f"{match.u2.profile.first_name}",
            },
            "u1_accepted": match.u1_accepted,
            "u2_accepted": match.u2_accepted,
            "accepted": match.accepted,
            "rejected": match.rejected,
            "in_session": match.in_session,
        }

        # Check if match is expired (users left lobby without accepting/rejecting)
        u1_in_lobby = active_lobby_users.filter(user=match.u1).exists()
        u2_in_lobby = active_lobby_users.filter(user=match.u2).exists()
        
        if match.accepted:
            accepted_matches.append(match_data)
        elif match.rejected:
            rejected_matches.append(match_data)
        elif not match.is_processed and (not u1_in_lobby or not u2_in_lobby):
            # Match is pending but at least one user left - expired
            expired_matches.append(match_data)
        elif not match.is_processed:
            # Match is pending and both users still in lobby
            pending_matches.append(match_data)

    # 7 - Calculate statistics
    statistics = {
        "total_matches": all_matches.count(),
        "pending_count": len(pending_matches),
        "accepted_count": len(accepted_matches),
        "rejected_count": len(rejected_matches),
        "expired_count": len(expired_matches),
    }

    # 8 - Build response
    response_data = {
        "lobby": {
            "name": lobby.name,
            "uuid": str(lobby.uuid),
            "is_active": lobby_active,
            "start_time": lobby.start_time.isoformat() if lobby.start_time else None,
            "end_time": lobby.end_time.isoformat() if lobby.end_time else None,
            "active_users_count": active_lobby_users.count(),
            "total_users_count": all_lobby_users.count(),
        },
        "active_users": active_users_data,
        "match_proposals": {
            "pending": pending_matches,
            "accepted": accepted_matches,
            "rejected": rejected_matches,
            "expired": expired_matches,
        },
        "statistics": statistics,
    }

    return Response(response_data)


# API URLs to be imported in urls.py
api_urls = [
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/overview",
        get_lobby_management_overview,
    ),
]
