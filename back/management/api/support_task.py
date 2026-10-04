from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.actions.registry import execute
from management.api.schema import (
    PaginatedSupportTaskResponse,
    SupportAssigneeUserEntrySerializer,
    SupportTaskOpenCountSerializer,
    SupportTaskStatsSerializer,
    SupportTaskUserSearchEntrySerializer,
)
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import DetailedPagination, IsAdminOrMatchingUser, IsAdminOrSupportUser
from management.models.support_task import (
    SupportTask,
    SupportTaskAction,
    SupportTaskActionSerializer,
    SupportTaskNote,
    SupportTaskNoteSerializer,
    SupportTaskSerializer,
)
from management.models.user import User
from management.permissions import support_users_queryset
from management.support_reply_outcomes import log_support_reply_outcome


def _users_for_ids(user_ids: list[int]) -> list[User]:
    unique_ids = list(dict.fromkeys(user_ids))
    users = list(User.objects.filter(pk__in=unique_ids))
    if len(users) != len(unique_ids):
        raise serializers.ValidationError({"assignee_ids": "One or more users do not exist."})
    users_by_id = {user.id: user for user in users}
    return [users_by_id[user_id] for user_id in unique_ids]


class CreateSupportTaskSerializer(serializers.Serializer):
    task_type = serializers.CharField()
    related_user_id = serializers.IntegerField()
    assignee_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    static_parameters = serializers.DictField(default=dict)
    parameters = serializers.DictField(default=dict)

    def create(self, validated_data):
        task_type = validated_data.pop("task_type")
        created_by = validated_data.pop("created_by")
        assignees = _users_for_ids(validated_data.pop("assignee_ids"))
        return SupportTask.create_of_type(task_type, created_by=created_by, assignees=assignees, **validated_data)


class BulkSupportTaskSerializer(serializers.Serializer):
    task_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    action = serializers.ChoiceField(choices=("delete", "complete", "cancel"))


def _apply_bulk_support_task_action(task, action, user):
    if action == "delete":
        task_id = task.pk
        task.delete()
        return task_id

    support_action = task.action
    if support_action.status != SupportTaskAction.Status.OPEN:
        raise ValueError("Action already processed")

    if action == "complete":
        execute(support_action)
        support_action.resolve(SupportTaskAction.Status.EXECUTED, user)
    elif action == "cancel":
        support_action.resolve(SupportTaskAction.Status.CANCELLED, user)
    else:
        raise ValueError(f"Unknown action: {action}")

    return task.pk


@extend_schema(
    request=BulkSupportTaskSerializer,
    responses={
        200: inline_serializer(
            name="BulkSupportTaskResponse",
            fields={
                "succeeded": serializers.ListField(child=serializers.IntegerField()),
                "failed": serializers.ListField(
                    child=inline_serializer(
                        name="BulkSupportTaskFailure",
                        fields={
                            "id": serializers.IntegerField(),
                            "error": serializers.CharField(),
                        },
                    )
                ),
            },
        )
    },
)
@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_bulk(request):
    serializer = BulkSupportTaskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    task_ids = serializer.validated_data["task_ids"]
    action = serializer.validated_data["action"]

    tasks = SupportTask.objects.select_related("action").filter(pk__in=task_ids)
    tasks_by_id = {task.pk: task for task in tasks}

    succeeded = []
    failed = []

    for task_id in task_ids:
        task = tasks_by_id.get(task_id)
        if task is None:
            failed.append({"id": task_id, "error": "Not found"})
            continue
        try:
            succeeded.append(_apply_bulk_support_task_action(task, action, request.user))
        except Exception as e:
            failed.append({"id": task_id, "error": str(e)})

    return Response({"succeeded": succeeded, "failed": failed})


class SupportTaskListQuerySerializer(serializers.Serializer):
    sort_by = serializers.ChoiceField(
        choices=("id", "priority", "status", "title", "created_at", "updated_at"),
        default="created_at",
        required=False,
    )
    sort_order = serializers.ChoiceField(choices=("asc", "desc"), default="desc", required=False)
    search = serializers.CharField(required=False, allow_blank=True)


@extend_schema(responses={200: PaginatedSupportTaskResponse})
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_list(request):
    tasks = (
        SupportTask.objects.select_related("action", "related_user__profile", "created_by__profile")
        .prefetch_related(
            "assignees__profile",
            "notes__completed_by__profile",
            "notes__created_by__profile",
            "notes__history__changed_by__profile",
        )
        .all()
    )

    serializer = SupportTaskListQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    query = serializer.validated_data

    status_filters = request.query_params.getlist("status")
    if status_filters:
        tasks = tasks.filter(status__in=status_filters)

    priority_filters = request.query_params.getlist("priority")
    if priority_filters:
        tasks = tasks.filter(priority__in=priority_filters)

    action_type_filters = request.query_params.getlist("action_type")
    if action_type_filters:
        tasks = tasks.filter(action__action_type__in=action_type_filters)

    assigned_to_raw = request.query_params.get("assigned_to")
    if assigned_to_raw == "unassigned":
        tasks = tasks.filter(assignees__isnull=True)
    elif assigned_to_raw:
        try:
            tasks = tasks.filter(assignees__id=int(assigned_to_raw))
        except ValueError:
            pass

    related_user_raw = request.query_params.get("related_user")
    if related_user_raw:
        try:
            tasks = tasks.filter(related_user_id=int(related_user_raw))
        except ValueError:
            pass

    search = query.get("search", "").strip()
    if search:
        q = Q(title__icontains=search)
        if search.isdigit():
            q |= Q(id=int(search))
        tasks = tasks.filter(q)

    sort_by = query["sort_by"]
    sort_order = query["sort_order"]
    order_prefix = "-" if sort_order == "desc" else ""

    valid_sort_fields = {"id", "status", "title", "created_at", "updated_at"}
    if sort_by == "priority":
        priority_rank = Case(
            When(priority="LOW", then=Value(1)),
            When(priority="MEDIUM", then=Value(2)),
            When(priority="HIGH", then=Value(3)),
            When(priority="URGENT", then=Value(4)),
            default=Value(0),
            output_field=IntegerField(),
        )
        tasks = tasks.annotate(priority_rank=priority_rank).order_by(f"{order_prefix}priority_rank")
    elif sort_by in valid_sort_fields:
        tasks = tasks.order_by(f"{order_prefix}{sort_by}")

    paginator = DetailedPagination()
    page_data = paginator.paginate_queryset(tasks.distinct(), request)
    return paginator.get_paginated_response(SupportTaskSerializer(page_data, many=True).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def support_task_create(request):
    serializer = CreateSupportTaskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        task = serializer.save(created_by=request.user)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(SupportTaskSerializer(task).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: SupportTaskSerializer})
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_detail(request, pk):
    try:
        task = (
            SupportTask.objects.select_related("action", "related_user__profile", "created_by__profile")
            .prefetch_related(
                "assignees__profile",
                "notes__completed_by__profile",
                "notes__created_by__profile",
                "notes__history__changed_by__profile",
            )
            .get(pk=pk)
        )
    except SupportTask.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(SupportTaskSerializer(task).data)


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_update(request, pk):
    try:
        task = SupportTask.objects.select_related("action").get(pk=pk)
    except SupportTask.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = SupportTaskSerializer(task, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(changed_by=request.user)
    task.claim_if_unassigned(request.user)
    return Response(SupportTaskSerializer(task).data)


@extend_schema(
    request=inline_serializer(
        name="SupportTaskActionUpdateRequest",
        fields={
            "parameters": serializers.DictField(
                required=False,
                help_text="Action-type-specific editable fields (e.g. support_reply uses message).",
            ),
        },
    ),
    responses={200: SupportTaskActionSerializer},
)
@api_view(["PATCH"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_action_update(request, task_pk):
    """Update dynamic parameters of a pending action (e.g. edit AI-generated draft)."""
    try:
        task = SupportTask.objects.select_related("action").get(pk=task_pk)
    except SupportTask.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    action = task.action

    if action.status != SupportTaskAction.Status.OPEN:
        return Response({"error": "Cannot edit a non-open action"}, status=status.HTTP_400_BAD_REQUEST)

    new_params = request.data.get("parameters")
    if new_params is not None:
        action.parameters = new_params
        action.save(update_fields=["parameters"], changed_by=request.user)
        task.claim_if_unassigned(request.user)

    return Response(SupportTaskActionSerializer(action).data)


def _support_reply_outcome_note(action: SupportTaskAction) -> str | None:
    """Return the audit note for a support_reply outcome that changes ticket state."""
    suggested_action = ((action.parameters or {}).get("suggested_action") or "reply").strip()
    if suggested_action == "mark_read":
        return "Message marked as read and ticket closed."
    if suggested_action == "slack_feedback":
        thread = ((action.parameters or {}).get("slack_thread") or "").strip() or "default"
        return f"Posted support feedback to Slack thread '{thread}' and closed the ticket."
    return None


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_action_execute(request, task_pk):
    """Approve an action — executes the underlying function after human confirmation."""
    try:
        task = SupportTask.objects.select_related("action").get(pk=task_pk)
    except SupportTask.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    action = task.action

    if action.status != SupportTaskAction.Status.OPEN:
        return Response({"error": "Action already processed"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        execute(action)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    if action.action_type == "support_reply":
        note_text = _support_reply_outcome_note(action)
        if note_text:
            log_support_reply_outcome(action, request.user, note_text)

    action.resolve(SupportTaskAction.Status.EXECUTED, request.user)
    return Response(SupportTaskActionSerializer(action).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_action_keep_open(request, task_pk):
    """Keep a support-reply task open for further processing, optionally rescheduling it."""
    try:
        task = SupportTask.objects.select_related("action").get(pk=task_pk)
    except SupportTask.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    action = task.action

    if action.action_type != "support_reply":
        return Response(
            {"error": "keep_open is only supported for support_reply actions"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if action.status != SupportTaskAction.Status.OPEN:
        return Response({"error": "Action already processed"}, status=status.HTTP_400_BAD_REQUEST)

    parameters = dict(action.parameters or {})
    provided = request.data.get("parameters")
    if isinstance(provided, dict):
        parameters.update(provided)
    else:
        for key in ("note", "scheduled_at", "message", "slack_message", "slack_thread"):
            if key in request.data:
                parameters[key] = request.data[key]
    parameters["suggested_action"] = "keep_open"

    scheduled_at = None
    scheduled_raw = (parameters.get("scheduled_at") or "").strip()
    if scheduled_raw:
        scheduled_at = parse_datetime(scheduled_raw)
        if scheduled_at is None:
            return Response({"error": "scheduled_at must be an ISO 8601 datetime"}, status=status.HTTP_400_BAD_REQUEST)
        if timezone.is_naive(scheduled_at):
            scheduled_at = timezone.make_aware(scheduled_at)

    action.parameters = parameters
    action.save(update_fields=["parameters"], changed_by=request.user)

    task.status = SupportTask.Status.IN_PROGRESS
    task.scheduled_at = scheduled_at
    task.save(update_fields=["status", "scheduled_at", "updated_at"], changed_by=request.user)

    note_text = (parameters.get("note") or "").strip()
    if note_text:
        log_support_reply_outcome(action, request.user, note_text)

    task.claim_if_unassigned(request.user)
    return Response(SupportTaskActionSerializer(action).data)


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def support_task_slack_threads(request):
    """List configured support-feedback Slack threads (keys/labels only, no secrets)."""
    from management.api.slack import list_support_feedback_threads

    return Response(list_support_feedback_threads())


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_action_cancel(request, task_pk):
    """Skip an action without executing it."""
    try:
        task = SupportTask.objects.select_related("action").get(pk=task_pk)
    except SupportTask.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    action = task.action

    if action.status != SupportTaskAction.Status.OPEN:
        return Response({"error": "Action already processed"}, status=status.HTTP_400_BAD_REQUEST)

    action.resolve(SupportTaskAction.Status.CANCELLED, request.user)
    return Response(SupportTaskActionSerializer(action).data)


@extend_schema(responses={200: SupportTaskStatsSerializer})
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_stats(request):
    rows = SupportTask.objects.values("status").annotate(count=Count("id"))
    counts = {row["status"]: row["count"] for row in rows}
    return Response(
        {
            "NEW": counts.get("NEW", 0),
            "IN_PROGRESS": counts.get("IN_PROGRESS", 0),
            "COMPLETED": counts.get("COMPLETED", 0),
        }
    )


@extend_schema(responses={200: SupportTaskOpenCountSerializer})
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def open_assigned_support_task_count(request, user_pk=None):
    user = request.user if user_pk is None else get_object_or_404(User, pk=user_pk)
    return Response({"count": user.open_assigned_support_task_count})


@extend_schema(responses={200: SupportAssigneeUserEntrySerializer(many=True)})
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def assignee_users(request):
    users = support_users_queryset().order_by("first_name", "last_name", "email")
    users = users.values("id", "email", "first_name", "last_name")
    return Response(list(users))


class CreateManualSupportTaskSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(default="", allow_blank=True)
    priority = serializers.ChoiceField(choices=SupportTask.Priority.choices, default=SupportTask.Priority.MEDIUM)
    related_user_id = serializers.IntegerField(required=False, allow_null=True)
    assignee_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_create_manual(request):
    serializer = CreateManualSupportTaskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    d = serializer.validated_data

    related_user_id = d.get("related_user_id")
    if related_user_id is not None and not User.objects.filter(pk=related_user_id).exists():
        return Response({"error": "Related user does not exist"}, status=status.HTTP_400_BAD_REQUEST)
    assignees = _users_for_ids(d["assignee_ids"])

    from django.db import transaction

    with transaction.atomic():
        task = SupportTask(
            title=d["title"],
            description=d.get("description", ""),
            priority=d["priority"],
            created_by=request.user,
            related_user_id=related_user_id,
        )
        task.save(changed_by=request.user)
        task.set_assignees(assignees, changed_by=request.user)
        action = SupportTaskAction(task=task, action_type="manual")
        action.save()

    task.refresh_from_db()
    return Response(SupportTaskSerializer(task).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: SupportTaskUserSearchEntrySerializer(many=True)})
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def user_search(request):
    q = request.query_params.get("q", "").strip()
    if not q:
        return Response([])
    qs = (
        User.objects.select_related("profile")
        .filter(Q(email__icontains=q) | Q(profile__first_name__icontains=q) | Q(profile__second_name__icontains=q))
        .distinct()[:20]
    )
    results = [
        {
            "id": u.id,
            "email": u.email,
            "first_name": u.profile.first_name if hasattr(u, "profile") else "",
            "second_name": u.profile.second_name if hasattr(u, "profile") else "",
        }
        for u in qs
    ]
    return Response(results)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_note_create(request, task_pk):
    try:
        task = SupportTask.objects.get(pk=task_pk)
    except SupportTask.DoesNotExist:
        return Response({"error": "Support task not found"}, status=status.HTTP_404_NOT_FOUND)

    text = (request.data.get("text") or "").strip()
    if not text:
        return Response({"error": "Note text is required"}, status=status.HTTP_400_BAD_REQUEST)

    note = SupportTaskNote(task=task, text=text, created_by=request.user)
    note.save(changed_by=request.user)
    task.claim_if_unassigned(request.user)
    return Response(SupportTaskNoteSerializer(note).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrSupportUser])
def support_task_note_detail(request, note_pk):
    """Edit a note's text and/or completion. Returns the updated note."""
    try:
        note = SupportTaskNote.objects.get(pk=note_pk)
    except SupportTaskNote.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    update_fields = []
    if "text" in request.data:
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"error": "Note text is required"}, status=status.HTTP_400_BAD_REQUEST)
        note.text = text
        update_fields.append("text")
    if "completed" in request.data:
        note.completed = bool(request.data["completed"])
        note.completed_at = timezone.now() if note.completed else None
        note.completed_by = request.user if note.completed else None
        update_fields += ["completed", "completed_at", "completed_by"]

    if update_fields:
        note.save(update_fields=update_fields, changed_by=request.user)
    return Response(SupportTaskNoteSerializer(note).data)


api_urls = [
    path("api/support_task/", support_task_list),
    path("api/support_task/bulk/", support_task_bulk),
    path("api/support_task/create/", support_task_create),
    path("api/support_task/create_manual/", support_task_create_manual),
    path("api/support_task/stats/", support_task_stats),
    path("api/support_task/open_assigned_count/", open_assigned_support_task_count),
    path("api/support_task/open_assigned_count/<int:user_pk>/", open_assigned_support_task_count),
    path("api/support_task/assignee_users/", assignee_users),
    path("api/support_task/user_search/", user_search),
    path("api/support_task/slack_threads/", support_task_slack_threads),
    path("api/support_task/<int:pk>/", support_task_detail),
    path("api/support_task/<int:pk>/update/", support_task_update),
    path("api/support_task/<int:task_pk>/action/", support_task_action_update),
    path("api/support_task/<int:task_pk>/action/execute/", support_task_action_execute),
    path("api/support_task/<int:task_pk>/action/keep_open/", support_task_action_keep_open),
    path("api/support_task/<int:task_pk>/action/cancel/", support_task_action_cancel),
    path("api/support_task/<int:task_pk>/notes/", support_task_note_create),
    path("api/support_task/notes/<int:note_pk>/", support_task_note_detail),
]
