from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.urls import path
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.actions.registry import execute
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import DetailedPagination, IsAdminOrMatchingUser
from management.models.support_task import (
    SupportTask,
    SupportTaskAction,
    SupportTaskActionSerializer,
    SupportTaskSerializer,
)
from management.models.user import User


class CreateSupportTaskSerializer(serializers.Serializer):
    task_type = serializers.CharField()
    related_user_id = serializers.IntegerField()
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True)
    static_parameters = serializers.DictField(default=dict)
    parameters = serializers.DictField(default=dict)

    def create(self, validated_data):
        task_type = validated_data.pop("task_type")
        created_by = validated_data.pop("created_by")
        return SupportTask.create_of_type(task_type, created_by=created_by, **validated_data)


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
@permission_classes([IsAdminOrMatchingUser])
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


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def support_task_list(request):
    tasks = SupportTask.objects.select_related(
        "action", "related_user__profile", "assigned_to__profile", "created_by__profile"
    ).all()

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
        tasks = tasks.filter(assigned_to__isnull=True)
    elif assigned_to_raw:
        try:
            tasks = tasks.filter(assigned_to_id=int(assigned_to_raw))
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
    page_data = paginator.paginate_queryset(tasks, request)
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


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def support_task_detail(request, pk):
    try:
        task = SupportTask.objects.select_related(
            "action", "related_user__profile", "assigned_to__profile", "created_by__profile"
        ).get(pk=pk)
    except SupportTask.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(SupportTaskSerializer(task).data)


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def support_task_update(request, pk):
    try:
        task = SupportTask.objects.select_related("action").get(pk=pk)
    except SupportTask.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = SupportTaskSerializer(task, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(changed_by=request.user)
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
@permission_classes([IsAdminOrMatchingUser])
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

    return Response(SupportTaskActionSerializer(action).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
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

    action.resolve(SupportTaskAction.Status.EXECUTED, request.user)
    return Response(SupportTaskActionSerializer(action).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
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


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
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


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def staff_users(request):
    users = User.objects.filter(is_staff=True).values("id", "email", "first_name", "last_name")
    return Response(list(users))


class CreateManualSupportTaskSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(default="", allow_blank=True)
    priority = serializers.ChoiceField(choices=SupportTask.Priority.choices, default=SupportTask.Priority.MEDIUM)
    related_user_id = serializers.IntegerField(required=False, allow_null=True)
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def support_task_create_manual(request):
    serializer = CreateManualSupportTaskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    d = serializer.validated_data

    related_user_id = d.get("related_user_id")
    assigned_to_id = d.get("assigned_to_id")

    from django.db import transaction

    with transaction.atomic():
        task = SupportTask(
            title=d["title"],
            description=d.get("description", ""),
            priority=d["priority"],
            created_by=request.user,
            related_user_id=related_user_id,
            assigned_to_id=assigned_to_id,
        )
        task.save(changed_by=request.user)
        action = SupportTaskAction(task=task, action_type="manual")
        action.save()

    task.refresh_from_db()
    return Response(SupportTaskSerializer(task).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
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


api_urls = [
    path("api/support_task/", support_task_list),
    path("api/support_task/bulk/", support_task_bulk),
    path("api/support_task/create/", support_task_create),
    path("api/support_task/create_manual/", support_task_create_manual),
    path("api/support_task/stats/", support_task_stats),
    path("api/support_task/staff_users/", staff_users),
    path("api/support_task/user_search/", user_search),
    path("api/support_task/<int:pk>/", support_task_detail),
    path("api/support_task/<int:pk>/update/", support_task_update),
    path("api/support_task/<int:task_pk>/action/", support_task_action_update),
    path("api/support_task/<int:task_pk>/action/execute/", support_task_action_execute),
    path("api/support_task/<int:task_pk>/action/cancel/", support_task_action_cancel),
]
