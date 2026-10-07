from calendar import monthrange
from datetime import datetime, timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.urls import path
from django.utils import timezone
from django_celery_results.models import TaskResult
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.models.event_frequency import EventFrequencyChoices
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from video.analytics.display_time import DISPLAY_TZ
from video.lobby_resolution import InvalidLobbyUuid, get_active_lobby, resolve_lobby_instance
from video.models import (
    RandomCallLobby,
    RandomCallLobbyUser,
    RandomCallMatching,
    RandomCallProposalUserStatus,
)


class RandomCallTaskSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    task_name = serializers.CharField()
    status = serializers.CharField()
    date_created = serializers.DateTimeField()
    date_done = serializers.DateTimeField(allow_null=True)
    result = serializers.CharField(allow_null=True)
    traceback = serializers.CharField(allow_null=True)
    worker = serializers.CharField(allow_null=True)


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

    lobby = resolve_lobby_instance(lobby_name)
    if lobby is None:
        return Response({"error": "Lobby not found"}, status=404)

    matches_qs = RandomCallMatching.objects.filter(
        Q(u1__uuid=user_uuid) | Q(u2__uuid=user_uuid),
        lobby=lobby,
        accepted=False,
        rejected=False,
        expired=False,
        completed=False,
    )
    match_ids = list(matches_qs.values_list("pk", flat=True))
    with transaction.atomic():
        if match_ids:
            updated_count = RandomCallMatching.objects.filter(pk__in=match_ids).update(expired=True)
            RandomCallMatching.objects.filter(pk__in=match_ids, u1_status=RandomCallProposalUserStatus.PENDING).update(
                u1_status=RandomCallProposalUserStatus.EXPIRED
            )
            RandomCallMatching.objects.filter(pk__in=match_ids, u2_status=RandomCallProposalUserStatus.PENDING).update(
                u2_status=RandomCallProposalUserStatus.EXPIRED
            )
        else:
            updated_count = 0

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
    lobby = resolve_lobby_instance(lobby_name)
    if lobby is None:
        return Response({"error": "Lobby not found"}, status=404)

    now = timezone.now()
    proposal_stale_threshold = now - timedelta(seconds=lobby.match_proposal_timeout)

    matches_qs = RandomCallMatching.objects.filter(
        lobby=lobby,
        accepted=False,
        rejected=False,
        expired=False,
        completed=False,
    ).filter(Q(created_at__lte=proposal_stale_threshold) | Q(created_at__isnull=True))
    match_ids = list(matches_qs.values_list("pk", flat=True))
    with transaction.atomic():
        if match_ids:
            updated_count = RandomCallMatching.objects.filter(pk__in=match_ids).update(expired=True)
            RandomCallMatching.objects.filter(pk__in=match_ids, u1_status=RandomCallProposalUserStatus.PENDING).update(
                u1_status=RandomCallProposalUserStatus.EXPIRED
            )
            RandomCallMatching.objects.filter(pk__in=match_ids, u2_status=RandomCallProposalUserStatus.PENDING).update(
                u2_status=RandomCallProposalUserStatus.EXPIRED
            )
        else:
            updated_count = 0

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
    existing_lobby = get_active_lobby(lobby_name)

    # Only reset an active lobby. With none active, a reset is only allowed when the
    # name has never been used, which bootstraps the first lobby.
    if existing_lobby is None and RandomCallLobby.objects.filter(name=lobby_name).exists():
        return Response(
            {
                "success": False,
                "message": f"Lobby '{lobby_name}' is not active and cannot be reset",
            },
            status=400,
        )

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


class CreateLobbySerializer(serializers.Serializer):
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    match_proposal_timeout = serializers.IntegerField(required=False, min_value=1, default=60)
    frequency = serializers.ChoiceField(
        choices=EventFrequencyChoices.choices,
        required=False,
        default=EventFrequencyChoices.ONCE,
    )


def _error_message(detail) -> str:
    """The first readable message in a DRF error detail.

    The admin panel shows ``error`` as an alert, and only does so when it is a string; a
    field dict reaches the admin as the bare "Bad Request".
    """
    if isinstance(detail, dict):
        if not detail:
            return "Invalid request"
        field, value = next(iter(detail.items()))
        message = _error_message(value)
        return message if field == "non_field_errors" else f"{field}: {message}"
    if isinstance(detail, list):
        return _error_message(detail[0]) if detail else "Invalid request"
    return str(detail)


def _local(value: datetime) -> datetime:
    """``value`` in the schedule timezone. The server runs in UTC, the admins do not."""
    return timezone.localtime(value, DISPLAY_TZ)


def _validate_lobby_times(start_time, end_time, *, require_future_start=False):
    current_time = timezone.now()
    if require_future_start and start_time <= current_time:
        raise serializers.ValidationError("Start time must be in the future")
    if not require_future_start and _local(start_time).date() < _local(current_time).date():
        raise serializers.ValidationError("Start time must be today or in the future")
    if end_time <= start_time:
        raise serializers.ValidationError("End time must be after start time")
    if _local(start_time).date() != _local(end_time).date():
        raise serializers.ValidationError("Start and end time must be on the same date")


def _add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _recurring_lobby_times(start_time, end_time, frequency):
    """Start and end of every occurrence from ``start_time`` to the end of its year.

    Steps are taken on Berlin wall-clock time, not in UTC, so a weekly 18:00 session stays
    at 18:00 when the clocks change instead of moving to 17:00 or 19:00.
    """
    yield start_time, end_time
    if frequency == EventFrequencyChoices.ONCE:
        return

    local_start = _local(start_time).replace(tzinfo=None)
    duration = _local(end_time).replace(tzinfo=None) - local_start
    occurrence = 1
    while True:
        if frequency == EventFrequencyChoices.WEEKLY:
            wall_start = local_start + timedelta(weeks=occurrence)
        elif frequency == EventFrequencyChoices.FORTNIGHTLY:
            wall_start = local_start + timedelta(weeks=2 * occurrence)
        else:
            wall_start = _add_months(local_start, occurrence)

        if wall_start.year != local_start.year:
            return

        yield wall_start.replace(tzinfo=DISPLAY_TZ), (wall_start + duration).replace(tzinfo=DISPLAY_TZ)
        occurrence += 1


def _validate_recurrence_year(start_time, frequency):
    if frequency != EventFrequencyChoices.ONCE and _local(start_time).year != _local(timezone.now()).year:
        raise serializers.ValidationError("Recurring lobbies can only be created within the current calendar year")


def _validate_no_overlap(lobby_name, times, *, exclude_pks=()):
    """Reject a schedule that overlaps another lobby with the same name.

    Lobbies of one name are a single queue: users join "the active default lobby", so two
    running at once would split them, and End/Reset could only ever act on one.
    """
    overlaps = Q()
    for occurrence_start, occurrence_end in times:
        overlaps |= Q(start_time__lt=occurrence_end, end_time__gt=occurrence_start)
    clash = (
        RandomCallLobby.objects.filter(overlaps, name=lobby_name)
        .exclude(pk__in=list(exclude_pks))
        .order_by("start_time")
        .first()
    )
    if clash:
        clash_start = _local(clash.start_time).strftime("%d.%m.%Y %H:%M")
        clash_end = _local(clash.end_time).strftime("%H:%M")
        raise serializers.ValidationError(f"Overlaps the existing '{lobby_name}' session on {clash_start}-{clash_end}")


def _sync_lobby_occurrences(
    *,
    existing,
    lobby_name,
    start_time,
    end_time,
    match_proposal_timeout,
    frequency,
):
    """Make ``existing`` (ordered by start) match the schedule, and return its lobbies.

    Existing lobbies are re-timed in place and only the difference is created or deleted,
    so a lobby keeps its uuid and anything attached to it when its series is edited.

    The lobbies always get a fresh recurrence group. Editing "this and future" splits the
    series at the edited lobby, as calendars do: the earlier part keeps the old group and
    ends where it now ends, instead of sharing one group with a schedule it no longer has.
    """
    recurrence_group = None if frequency == EventFrequencyChoices.ONCE else uuid4()
    times = list(_recurring_lobby_times(start_time, end_time, frequency))
    existing = list(existing)

    kept = existing[: len(times)]
    for lobby, (occurrence_start, occurrence_end) in zip(kept, times):
        lobby.start_time = occurrence_start
        lobby.end_time = occurrence_end
        lobby.match_proposal_timeout = match_proposal_timeout
        lobby.frequency = frequency
        lobby.recurrence_group = recurrence_group
    RandomCallLobby.objects.bulk_update(
        kept,
        ["start_time", "end_time", "match_proposal_timeout", "frequency", "recurrence_group"],
    )
    RandomCallLobby.objects.filter(pk__in=[lobby.pk for lobby in existing[len(times) :]]).delete()

    created = RandomCallLobby.objects.bulk_create(
        [
            RandomCallLobby(
                name=lobby_name,
                start_time=occurrence_start,
                end_time=occurrence_end,
                user_online_state_timeout=10,
                match_proposal_timeout=match_proposal_timeout,
                video_call_timeout=60 * 10,
                frequency=frequency,
                recurrence_group=recurrence_group,
            )
            for occurrence_start, occurrence_end in times[len(kept) :]
        ]
    )
    return kept + created


def _lobby_payload(lobby):
    return {
        "name": lobby.name,
        "uuid": str(lobby.uuid),
        "start_time": lobby.start_time.isoformat(),
        "end_time": lobby.end_time.isoformat(),
        "match_proposal_timeout": lobby.match_proposal_timeout,
        "frequency": lobby.frequency,
        "recurrence_group": str(lobby.recurrence_group) if lobby.recurrence_group else None,
    }


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def create_lobby(request, lobby_name):
    """
    Admin API to create a new lobby with the specified name, start_time, and end_time.
    """
    serializer = CreateLobbySerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _error_message(serializer.errors)}, status=400)

    start_time = serializer.validated_data["start_time"]
    end_time = serializer.validated_data["end_time"]
    match_proposal_timeout = serializer.validated_data.get("match_proposal_timeout", 60)
    frequency = serializer.validated_data["frequency"]

    try:
        _validate_lobby_times(start_time, end_time)
        _validate_recurrence_year(start_time, frequency)
        _validate_no_overlap(lobby_name, _recurring_lobby_times(start_time, end_time, frequency))
    except serializers.ValidationError as error:
        return Response({"error": _error_message(error.detail)}, status=400)

    with transaction.atomic():
        lobbies = _sync_lobby_occurrences(
            existing=[],
            lobby_name=lobby_name,
            start_time=start_time,
            end_time=end_time,
            match_proposal_timeout=match_proposal_timeout,
            frequency=frequency,
        )
    lobby = lobbies[0]

    return Response(
        {
            "success": True,
            "message": f"Lobby '{lobby_name}' has been created",
            "lobby": _lobby_payload(lobby),
            "created_count": len(lobbies),
        },
        status=201,
    )


@api_view(["PATCH", "DELETE"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def manage_upcoming_lobby(request, lobby_uuid):
    try:
        lobby = RandomCallLobby.objects.get(uuid=lobby_uuid)
    except RandomCallLobby.DoesNotExist:
        return Response({"error": "Lobby not found"}, status=404)

    if lobby.start_time is None or lobby.start_time <= timezone.now():
        return Response({"error": "Only upcoming lobbies can be edited or deleted"}, status=400)

    scope = request.query_params.get("scope", "single")
    if scope not in {"single", "future"}:
        return Response({"error": "Scope must be 'single' or 'future'"}, status=400)

    if scope == "future" and lobby.recurrence_group:
        series = RandomCallLobby.objects.filter(
            recurrence_group=lobby.recurrence_group,
            start_time__gte=lobby.start_time,
        ).order_by("start_time")
    else:
        series = RandomCallLobby.objects.filter(pk=lobby.pk)

    if request.method == "DELETE":
        deleted_count = series.count()
        series.delete()
        return Response({"success": True, "deleted_count": deleted_count})

    serializer = CreateLobbySerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _error_message(serializer.errors)}, status=400)

    start_time = serializer.validated_data["start_time"]
    end_time = serializer.validated_data["end_time"]
    # An edit that leaves frequency out keeps the lobby's own, rather than the "once" default.
    frequency = serializer.validated_data["frequency"] if "frequency" in request.data else lobby.frequency
    match_proposal_timeout = serializer.validated_data.get("match_proposal_timeout", 60)
    # A single edit only re-times this lobby; a series edit replaces the whole series.
    new_times = (
        [(start_time, end_time)] if scope == "single" else _recurring_lobby_times(start_time, end_time, frequency)
    )
    try:
        _validate_lobby_times(start_time, end_time, require_future_start=True)
        _validate_recurrence_year(start_time, frequency)
        _validate_no_overlap(lobby.name, new_times, exclude_pks=series.values_list("pk", flat=True))
    except serializers.ValidationError as error:
        return Response({"error": _error_message(error.detail)}, status=400)

    if scope == "single":
        if frequency != lobby.frequency:
            return Response(
                {"error": "Changing recurrence requires updating this and future sessions"},
                status=400,
            )
        lobby.start_time = start_time
        lobby.end_time = end_time
        lobby.match_proposal_timeout = match_proposal_timeout
        lobby.save(update_fields=["start_time", "end_time", "match_proposal_timeout"])
        updated_lobbies = [lobby]
    else:
        with transaction.atomic():
            updated_lobbies = _sync_lobby_occurrences(
                existing=series,
                lobby_name=lobby.name,
                start_time=start_time,
                end_time=end_time,
                match_proposal_timeout=match_proposal_timeout,
                frequency=frequency,
            )
        lobby = updated_lobbies[0]

    return Response(
        {
            "success": True,
            "message": f"Lobby '{lobby.name}' has been updated",
            "lobby": _lobby_payload(lobby),
            "updated_count": len(updated_lobbies),
        }
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def end_lobby(request, lobby_name="default"):
    """
    Admin API to end an active lobby by setting end_time to current time.
    Only ends the lobby if it is currently active.
    """
    lobby = get_active_lobby(lobby_name)
    if lobby is None:
        if not RandomCallLobby.objects.filter(name=lobby_name).exists():
            return Response({"error": "Lobby not found"}, status=404)
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
        lobby = resolve_lobby_instance(lobby_name, lobby_uuid=lobby_uuid_param)
    except InvalidLobbyUuid:
        return Response({"error": "Invalid lobby_uuid"}, status=400)
    if lobby is None:
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
        "api/random_calls/lobby/<uuid:lobby_uuid>/management",
        manage_upcoming_lobby,
    ),
    path(
        "api/random_calls/lobby/<str:lobby_name>/management/end",
        end_lobby,
    ),
]
