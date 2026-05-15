from datetime import timedelta

from django.db.models import Q
from django.urls import path
from django.utils import timezone
from django_celery_results.models import TaskResult
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.models.profile import Profile
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
from video.random_calls import (
    get_pending_random_call_matching_qs_for_user,
    is_lobby_active,
)


def _resolve_management_lobby(lobby_name: str):
    """
    Same lobby resolution as the management overview: active lobby for name,
    else most recent finished lobby with that name.
    """
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


def _get_lobby_for_overview(lobby_name: str, lobby_uuid=None):
    """
    Resolve the lobby for management overview.
    - If lobby_uuid is provided, return that exact lobby instance.
    - Else, keep existing behavior (active lobby by name, else most recent finished).
    """
    if lobby_uuid:
        return RandomCallLobby.objects.get(uuid=lobby_uuid)
    return _resolve_management_lobby(lobby_name)


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
    user_uuid = serializers.CharField()
    user_name = serializers.CharField()
    user_type = serializers.ChoiceField(choices=Profile.TypeChoices.choices, required=True)
    is_active = serializers.BooleanField()
    last_status_checked_at = serializers.DateTimeField(allow_null=True)
    has_pending_match = serializers.BooleanField()


class RandomCallMatchSerializer(serializers.Serializer):
    uuid = serializers.CharField()
    u1_uuid = serializers.CharField()
    u1_name = serializers.CharField()
    u1_user_type = serializers.ChoiceField(choices=Profile.TypeChoices.choices, required=True)
    u2_uuid = serializers.CharField()
    u2_name = serializers.CharField()
    u2_user_type = serializers.ChoiceField(choices=Profile.TypeChoices.choices, required=True)
    u1_accepted = serializers.BooleanField()
    u2_accepted = serializers.BooleanField()
    accepted = serializers.BooleanField()
    rejected = serializers.BooleanField()
    expired = serializers.BooleanField()
    completed = serializers.BooleanField()
    in_session = serializers.BooleanField()
    created_at = serializers.DateTimeField(allow_null=True, required=False)


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
    now = timezone.now()
    lobby_uuid_param = request.query_params.get("lobby_uuid", None)
    try:
        lobby = _get_lobby_for_overview(lobby_name, lobby_uuid=lobby_uuid_param)
    except RandomCallLobby.DoesNotExist:
        return Response({"error": "Lobby not found"}, status=404)
    if lobby is None:
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

    # 5 - Get all match proposals for this lobby
    all_matches = RandomCallMatching.objects.filter(lobby=lobby).select_related("u1", "u2")

    # 6 - Categorize matches by status
    pending_matches = []
    accepted_matches = []
    rejected_matches = []
    expired_matches = []
    dangling_matches = []

    proposal_stale_threshold = now - timedelta(seconds=lobby.match_proposal_timeout)

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
            "accepted": match.accepted,
            "rejected": match.rejected,
            "expired": match.expired,
            "completed": match.completed,
            "in_session": match.in_session,
            "created_at": match.created_at,
        }

        # Check if match is expired (users left lobby without accepting/rejecting)
        u1_in_lobby = active_lobby_users.filter(user=match.u1).exists()
        u2_in_lobby = active_lobby_users.filter(user=match.u2).exists()

        # Check if match is expired first (before checking accepted/rejected)
        is_expired = match.expired or (not match.is_processed and (not u1_in_lobby or not u2_in_lobby))

        is_dangling_open = (
            not match.accepted
            and not match.rejected
            and not match.expired
            and not match.completed
            and (match.created_at is None or match.created_at <= proposal_stale_threshold)
        )

        if match.accepted:
            accepted_matches.append(match_data)
        elif is_expired:
            # Match is expired (either timeout or users left lobby)
            expired_matches.append(match_data)
        elif match.rejected:
            rejected_matches.append(match_data)
        elif is_dangling_open:
            dangling_matches.append(match_data)
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
        "dangling_count": len(dangling_matches),
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
            "dangling": RandomCallMatchSerializer(dangling_matches, many=True).data,
        },
        "statistics": statistics,
    }

    return Response(response_data)


class ClearUserProposalsSerializer(serializers.Serializer):
    user_uuid = serializers.CharField()


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def clear_user_random_call_proposals(request, lobby_name="default"):
    """
    Admin API to clear dangling random call proposals for a specific user.
    Closes dangling random-call matchings where the user is involved.
    """
    serializer = ClearUserProposalsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=400)

    user_uuid = serializer.validated_data["user_uuid"]

    updated_count = RandomCallMatching.objects.filter(
        Q(u1__uuid=user_uuid) | Q(u2__uuid=user_uuid),
        accepted=False,
        rejected=False,
        expired=False,
        completed=False,
    ).update(expired=True)

    return Response(
        {
            "success": True,
            "message": "Random call proposals cleared successfully",
            "updated_count": updated_count,
            "user_uuid": user_uuid,
        },
        status=200,
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def clear_dangling_random_call_proposals(request, lobby_name="default"):
    """
    Admin API: mark all dangling random-call proposals for this lobby as expired.

    Dangling = not accepted, not rejected, not expired, not completed, and
    created_at is older than lobby.match_proposal_timeout (or created_at is null).
    """
    lobby = _resolve_management_lobby(lobby_name)
    if lobby is None:
        return Response({"error": "Lobby not found"}, status=404)

    now = timezone.now()
    proposal_stale_threshold = now - timedelta(seconds=lobby.match_proposal_timeout)

    updated_count = (
        RandomCallMatching.objects.filter(
            lobby=lobby,
            accepted=False,
            rejected=False,
            expired=False,
            completed=False,
        )
        .filter(Q(created_at__lte=proposal_stale_threshold) | Q(created_at__isnull=True))
        .update(expired=True)
    )

    return Response(
        {
            "success": True,
            "message": "Dangling random call matches cleared",
            "updated_count": updated_count,
        },
        status=200,
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def reset_default_lobby(request, lobby_name="default"):
    """
    Admin API to reset the default random call lobby.
    Deletes all lobby users, matchings, and recreates the lobby with current time.
    Only resets if the existing lobby is active.
    """
    # Get the most recent lobby with this name
    existing_lobby = RandomCallLobby.objects.filter(name=lobby_name).order_by("-id").first()

    if existing_lobby:
        # Only reset if the lobby is active
        if not is_lobby_active(existing_lobby):
            return Response(
                {
                    "success": False,
                    "message": f"Lobby '{lobby_name}' is not active and cannot be reset",
                },
                status=400,
            )

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


class CreateLobbySerializer(serializers.Serializer):
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    match_proposal_timeout = serializers.IntegerField(required=False, min_value=1, default=60)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def create_lobby(request, lobby_name):
    """
    Admin API to create a new lobby with the specified name, start_time, and end_time.
    """
    serializer = CreateLobbySerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=400)

    start_time = serializer.validated_data["start_time"]
    end_time = serializer.validated_data["end_time"]
    match_proposal_timeout = serializer.validated_data.get("match_proposal_timeout", 60)
    current_time = timezone.now()

    # Validate that start_time is not before today (today is allowed, even if earlier than now)
    if start_time.date() < current_time.date():
        return Response(
            {"error": "Start time must be today or in the future"},
            status=400,
        )

    # Validate that end_time is after start_time
    if end_time <= start_time:
        return Response(
            {"error": "End time must be after start time"},
            status=400,
        )

    # Create new lobby
    lobby = RandomCallLobby.objects.create(
        name=lobby_name,
        start_time=start_time,
        end_time=end_time,
        user_online_state_timeout=10,
        match_proposal_timeout=match_proposal_timeout,
        video_call_timeout=60 * 10,
    )

    return Response(
        {
            "success": True,
            "message": f"Lobby '{lobby_name}' has been created",
            "lobby": {
                "name": lobby.name,
                "uuid": str(lobby.uuid),
                "start_time": lobby.start_time.isoformat(),
                "end_time": lobby.end_time.isoformat(),
            },
        },
        status=201,
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def end_lobby(request, lobby_name="default"):
    """
    Admin API to end an active lobby by setting end_time to current time.
    Only ends the lobby if it is currently active.
    """
    try:
        lobby = RandomCallLobby.objects.filter(name=lobby_name).order_by("-id").first()
        if lobby is None:
            raise RandomCallLobby.DoesNotExist
    except RandomCallLobby.DoesNotExist:
        return Response({"error": "Lobby not found"}, status=404)

    # Check if the lobby is active
    if not is_lobby_active(lobby):
        return Response(
            {
                "success": False,
                "message": f"Lobby '{lobby_name}' is not active and cannot be ended",
            },
            status=400,
        )

    # Update end_time to current time
    lobby.end_time = timezone.now()
    lobby.save()

    return Response(
        {
            "success": True,
            "message": f"Lobby '{lobby_name}' has been ended",
            "lobby": {
                "name": lobby.name,
                "uuid": str(lobby.uuid),
                "start_time": lobby.start_time.isoformat() if lobby.start_time else None,
                "end_time": lobby.end_time.isoformat(),
            },
        },
        status=200,
    )


def _get_lobby_for_tasks(lobby_name, lobby_uuid=None):
    """
    Resolve the lobby to use for task filtering.
    - If lobby_uuid is given: return that lobby instance (404 if not found).
    - Else: return the active lobby with that name, or the most recent past one.
    """
    if lobby_uuid:
        return RandomCallLobby.objects.get(uuid=lobby_uuid)

    now = timezone.now()
    # Active lobby
    lobby = (
        RandomCallLobby.objects.filter(
            name=lobby_name,
            start_time__lte=now,
            end_time__gte=now,
        )
        .order_by("-id")
        .first()
    )
    if lobby is not None:
        return lobby
    # Most recent past lobby
    lobby = (
        RandomCallLobby.objects.filter(
            name=lobby_name,
            end_time__lt=now,
        )
        .order_by("-end_time")
        .first()
    )
    if lobby is None:
        raise RandomCallLobby.DoesNotExist
    return lobby


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def get_random_call_tasks(request, lobby_name="default"):
    """
    Admin API to get Celery task information for random call related tasks,
    scoped to a lobby.

    Query params:
    - lobby_uuid (optional): If set, return tasks only for this lobby instance.
      If omitted, return tasks for the active lobby with lobby_name, or the
      most recent finished lobby with that name.
    - limit: Max number of task rows (default 50).
    - task_name: Optional filter by task name.

    Tasks that take a lobby UUID in args (perform_matching, cleanup_inactive_lobby_users)
    are filtered by that lobby. Other task types are excluded when scoping by lobby.
    """
    import json

    # Only these tasks receive lobby_uuid in args; others are not scoped by lobby
    task_names_with_lobby_arg = [
        "video.tasks.random_call_lobby_perform_matching",
        "video.tasks.cleanup_inactive_lobby_users",
    ]

    lobby_uuid_param = request.query_params.get("lobby_uuid", None)
    limit = int(request.query_params.get("limit", 50))
    task_name_filter = request.query_params.get("task_name", None)

    try:
        lobby = _get_lobby_for_tasks(lobby_name, lobby_uuid=lobby_uuid_param)
    except RandomCallLobby.DoesNotExist:
        return Response({"error": "Lobby not found"}, status=404)

    lobby_uuid_str = str(lobby.uuid)

    task_query = TaskResult.objects.filter(
        task_name__in=task_names_with_lobby_arg,
        task_args__contains=lobby_uuid_str,
    )

    if task_name_filter:
        task_query = task_query.filter(task_name=task_name_filter)

    tasks = task_query.order_by("-date_created")[:limit]

    tasks_data = []
    for task in tasks:
        result_str = None
        if task.result:
            try:
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

    base_filter = TaskResult.objects.filter(
        task_name__in=task_names_with_lobby_arg,
        task_args__contains=lobby_uuid_str,
    )

    total_tasks = base_filter.count()
    successful_tasks = base_filter.filter(status="SUCCESS").count()
    failed_tasks = base_filter.filter(status="FAILURE").count()
    pending_tasks = base_filter.filter(status="PENDING").count()

    task_stats = {}
    for task_name in task_names_with_lobby_arg:
        q = base_filter.filter(task_name=task_name)
        task_stats[task_name] = {
            "total": q.count(),
            "success": q.filter(status="SUCCESS").count(),
            "failure": q.filter(status="FAILURE").count(),
            "pending": q.filter(status="PENDING").count(),
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
            "lobby": {
                "uuid": str(lobby.uuid),
                "name": lobby.name,
            },
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
        "api/random_calls/lobby/<str:lobby_name>/management/clear-user-proposals",
        clear_user_random_call_proposals,
    ),
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/clear-dangling-proposals",
        clear_dangling_random_call_proposals,
    ),
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/tasks",
        get_random_call_tasks,
    ),
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/create",
        create_lobby,
    ),
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/end",
        end_lobby,
    ),
]
