from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.urls import path
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.actions.registry import execute
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
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


class SupportTaskListQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SupportTask.Status.choices, required=False)
    assigned_to = serializers.IntegerField(required=False)
    sort_by = serializers.ChoiceField(
        choices=("id", "priority", "status", "title", "created_at", "updated_at"),
        default="created_at",
        required=False,
    )
    sort_order = serializers.ChoiceField(choices=("asc", "desc"), default="desc", required=False)


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

    status_filter = query.get("status")
    if status_filter:
        tasks = tasks.filter(status=status_filter)

    assigned_to = query.get("assigned_to")
    if assigned_to:
        tasks = tasks.filter(assigned_to=assigned_to)

    sort_by = query["sort_by"]
    sort_order = query["sort_order"]

    order_prefix = ""
    if sort_order == "desc":
        order_prefix = "-"

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

    return Response(SupportTaskSerializer(tasks, many=True).data)


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
        .filter(
            Q(email__icontains=q)
            | Q(profile__first_name__icontains=q)
            | Q(profile__second_name__icontains=q)
        )
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
