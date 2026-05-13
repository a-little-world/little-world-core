from django.urls import path
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from management.actions.registry import execute
from management.authentication import NativeOnlyJWTAuthentication
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


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def support_task_list(request):
    tasks = SupportTask.objects.select_related(
        "action", "related_user__profile", "assigned_to__profile", "created_by__profile"
    ).all()

    status_filter = request.query_params.get("status")
    if status_filter:
        tasks = tasks.filter(status=status_filter)

    assigned_to = request.query_params.get("assigned_to")
    if assigned_to:
        tasks = tasks.filter(assigned_to_id=assigned_to)

    sort_by = request.query_params.get("sort_by", "created_at")
    sort_order = request.query_params.get("sort_order", "desc")

    valid_sort_fields = {"status", "title", "created_at"}
    if sort_by in valid_sort_fields:
        order_prefix = "-" if sort_order == "desc" else ""
        tasks = tasks.order_by(f"{order_prefix}{sort_by}")

    return Response(SupportTaskSerializer(tasks, many=True).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def support_task_create(request):
    serializer = CreateSupportTaskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    d = serializer.validated_data
    try:
        task = SupportTask.create_of_type(
            d["task_type"],
            static_parameters=d["static_parameters"],
            parameters=d["parameters"],
            related_user_id=d["related_user_id"],
            assigned_to_id=d.get("assigned_to_id"),
            created_by=request.user,
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(SupportTaskSerializer(task).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
def staff_users(request):
    users = User.objects.filter(is_staff=True).values("id", "email", "first_name", "last_name")
    return Response(list(users))


api_urls = [
    path("api/support_task/", support_task_list),
    path("api/support_task/create/", support_task_create),
    path("api/support_task/staff_users/", staff_users),
    path("api/support_task/<int:pk>/", support_task_detail),
    path("api/support_task/<int:pk>/update/", support_task_update),
    path("api/support_task/<int:task_pk>/action/", support_task_action_update),
    path("api/support_task/<int:task_pk>/action/execute/", support_task_action_execute),
    path("api/support_task/<int:task_pk>/action/cancel/", support_task_action_cancel),
]
