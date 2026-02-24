from datetime import timedelta

from django.db.models import Q
from django.urls import path
from django.utils import timezone
from django_celery_results.models import TaskResult
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from video.models import (
    RandomCallLobby,
    RandomCallLobbyUser,
    RandomCallMatching,
)
from video.random_calls import is_lobby_active


class RandomCallLobbyManagementSerializer(serializers.Serializer):
    name = serializers.CharField()
    uuid = serializers.CharField()
    is_active = serializers.BooleanField()
    start_time = serializers.DateTimeField(allow_null=True)
    end_time = serializers.DateTimeField(allow_null=True)
    active_users_count = serializers.IntegerField()
    total_users_count = serializers.IntegerField()


class RandomCallUserSerializer(serializers.Serializer):
    uuid = serializers.CharField()
    user_hash = serializers.CharField()
    user_name = serializers.CharField()
    is_active = serializers.BooleanField()
    last_status_checked_at = serializers.DateTimeField(allow_null=True)
    has_pending_match = serializers.BooleanField()


class RandomCallMatchSerializer(serializers.Serializer):
    uuid = serializers.CharField()
    u1_hash = serializers.CharField()
    u1_name = serializers.CharField()
    u2_hash = serializers.CharField()
    u2_name = serializers.CharField()
    u1_accepted = serializers.BooleanField()
    u2_accepted = serializers.BooleanField()
    accepted = serializers.BooleanField()
    rejected = serializers.BooleanField()
    expired = serializers.BooleanField()
    in_session = serializers.BooleanField()


class RandomCallTaskSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    task_name = serializers.CharField()
    status = serializers.CharField()
    date_created = serializers.DateTimeField()
    date_done = serializers.DateTimeField(allow_null=True)
    result = serializers.CharField(allow_null=True)
    traceback = serializers.CharField(allow_null=True)
    worker = serializers.CharField(allow_null=True)


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
            Q(u1=user) | Q(u2=user), lobby=lobby, rejected=False, accepted=False
        ).exists()

        active_users_data.append(
            {
                "uuid": str(lobby_user.uuid),
                "user_hash": user.hash,
                "user_name": f"{user.profile.first_name}",
                "is_active": lobby_user.is_active,
                "last_status_checked_at": lobby_user.last_status_checked_at.isoformat()
                if lobby_user.last_status_checked_at
                else None,
                "has_pending_match": has_pending_match,
            }
        )

    # 5 - Get all match proposals for this lobby
    all_matches = RandomCallMatching.objects.filter(lobby=lobby).select_related("u1", "u2")

    # 6 - Categorize matches by status
    pending_matches = []
    accepted_matches = []
    rejected_matches = []
    expired_matches = []

    for match in all_matches:
        match_data = {
            "uuid": str(match.uuid),
            "u1_hash": match.u1.hash,
            "u1_name": f"{match.u1.profile.first_name}",
            "u2_hash": match.u2.hash,
            "u2_name": f"{match.u2.profile.first_name}",
            "u1_accepted": match.u1_accepted,
            "u2_accepted": match.u2_accepted,
            "accepted": match.accepted,
            "rejected": match.rejected,
            "expired": match.expired,
            "in_session": match.in_session,
        }

        # Check if match is expired (users left lobby without accepting/rejecting)
        u1_in_lobby = active_lobby_users.filter(user=match.u1).exists()
        u2_in_lobby = active_lobby_users.filter(user=match.u2).exists()

        # Check if match is expired first (before checking accepted/rejected)
        is_expired = match.expired or (not match.is_processed and (not u1_in_lobby or not u2_in_lobby))

        if match.accepted:
            accepted_matches.append(match_data)
        elif is_expired:
            # Match is expired (either timeout or users left lobby)
            expired_matches.append(match_data)
        elif match.rejected:
            rejected_matches.append(match_data)
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

    # 8 - Build response using serializers following the pattern from the codebase
    lobby_data = {
        "name": lobby.name,
        "uuid": str(lobby.uuid),
        "is_active": lobby_active,
        "start_time": lobby.start_time.isoformat() if lobby.start_time else None,
        "end_time": lobby.end_time.isoformat() if lobby.end_time else None,
        "active_users_count": active_lobby_users.count(),
        "total_users_count": all_lobby_users.count(),
    }

    # Serialize all data following the pattern from the existing codebase
    response_data = {
        "lobby": RandomCallLobbyManagementSerializer(lobby_data).data,
        "active_users": RandomCallUserSerializer(active_users_data, many=True).data,
        "match_proposals": {
            "pending": RandomCallMatchSerializer(pending_matches, many=True).data,
            "accepted": RandomCallMatchSerializer(accepted_matches, many=True).data,
            "rejected": RandomCallMatchSerializer(rejected_matches, many=True).data,
            "expired": RandomCallMatchSerializer(expired_matches, many=True).data,
        },
        "statistics": statistics,
    }

    return Response(response_data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def reset_default_lobby(request, lobby_name="default"):
    """
    Admin API to reset the default random call lobby.
    Deletes all lobby users, matchings, and recreates the lobby with current time.
    """
    # Get the existing lobby first
    existing_lobby = RandomCallLobby.objects.filter(name=lobby_name).first()

    if existing_lobby:
        # Clear all lobby users
        RandomCallLobbyUser.objects.filter(lobby=existing_lobby).delete()

        # Clear all matchings
        RandomCallMatching.objects.filter(lobby=existing_lobby).delete()

        # Delete the lobby itself
        existing_lobby.delete()

    # Create new default lobby with current time
    lobby = RandomCallLobby.objects.create(name=lobby_name)
    lobby.start_time = timezone.now()
    lobby.end_time = timezone.now() + timedelta(hours=2)
    lobby.user_online_state_timeout = 10
    lobby.match_proposal_timeout = 30
    lobby.video_call_timeout = 60 * 10

    lobby.save()

    return Response(
        {
            "success": True,
            "message": f"Lobby '{lobby_name}' has been reset",
            "lobby": {
                "name": lobby.name,
                "uuid": str(lobby.uuid),
                "start_time": lobby.start_time.isoformat(),
                "end_time": lobby.end_time.isoformat(),
            },
        },
        status=200,
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def get_random_call_tasks(request, lobby_name="default"):
    """
    Admin API to get Celery task information for random call related tasks.
    Returns recent task executions for:
    - random_call_lobby_perform_matching
    - cleanup_inactive_lobby_users
    - cleanup_if_not_accepted
    - create_default_random_call_lobby
    """
    # Define the task names we're interested in
    random_call_task_names = [
        "video.tasks.random_call_lobby_perform_matching",
        "video.tasks.cleanup_inactive_lobby_users",
        "video.tasks.cleanup_if_not_accepted",
        "video.tasks.create_default_random_call_lobby",
    ]

    # Get query parameters
    limit = int(request.query_params.get("limit", 50))
    task_name_filter = request.query_params.get("task_name", None)

    # Build query
    task_query = TaskResult.objects.filter(task_name__in=random_call_task_names)

    # Filter by specific task name if provided
    if task_name_filter:
        task_query = task_query.filter(task_name=task_name_filter)

    # Order by most recent first and limit results
    tasks = task_query.order_by("-date_created")[:limit]

    # Serialize task data
    tasks_data = []
    for task in tasks:
        # Parse result if it's a string
        result_str = None
        if task.result:
            try:
                import json

                result_str = json.dumps(task.result) if not isinstance(task.result, str) else task.result
            except (TypeError, ValueError):
                result_str = str(task.result)

        tasks_data.append(
            {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "status": task.status,
                "date_created": task.date_created.isoformat() if task.date_created else None,
                "date_done": task.date_done.isoformat() if task.date_done else None,
                "result": result_str,
                "traceback": task.traceback,
                "worker": task.worker,
            }
        )

    # Get statistics
    total_tasks = TaskResult.objects.filter(task_name__in=random_call_task_names).count()
    successful_tasks = TaskResult.objects.filter(task_name__in=random_call_task_names, status="SUCCESS").count()
    failed_tasks = TaskResult.objects.filter(task_name__in=random_call_task_names, status="FAILURE").count()
    pending_tasks = TaskResult.objects.filter(task_name__in=random_call_task_names, status="PENDING").count()

    # Group by task name for statistics
    task_stats = {}
    for task_name in random_call_task_names:
        task_stats[task_name] = {
            "total": TaskResult.objects.filter(task_name=task_name).count(),
            "success": TaskResult.objects.filter(task_name=task_name, status="SUCCESS").count(),
            "failure": TaskResult.objects.filter(task_name=task_name, status="FAILURE").count(),
            "pending": TaskResult.objects.filter(task_name=task_name, status="PENDING").count(),
        }

    return Response(
        {
            "tasks": RandomCallTaskSerializer(tasks_data, many=True).data,
            "statistics": {
                "total": total_tasks,
                "success": successful_tasks,
                "failure": failed_tasks,
                "pending": pending_tasks,
            },
            "task_statistics": task_stats,
        },
        status=200,
    )


# API URLs to be imported in urls.py
api_urls = [
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/overview",
        get_lobby_management_overview,
    ),
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/reset",
        reset_default_lobby,
    ),
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/tasks",
        get_random_call_tasks,
    ),
]
