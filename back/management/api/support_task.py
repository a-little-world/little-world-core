from actions.registry import execute
from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from models import SupportTask, SupportTaskAction, SupportTaskReminder
from rest_framework import authentication, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from serializers import SupportTaskActionSerializer, SupportTaskReminderSerializer, SupportTaskSerializer

from management.models.user import User

_AUTH = [authentication.SessionAuthentication, authentication.BasicAuthentication]
_PERMS = [permissions.IsAuthenticated]


class SupportTaskListView(APIView):
    authentication_classes = _AUTH
    permission_classes = _PERMS

    @extend_schema(responses=SupportTaskSerializer(many=True))
    def get(self, request):
        qs = SupportTask.objects.prefetch_related("actions").all()

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        assigned_to = request.query_params.get("assigned_to")
        if assigned_to:
            qs = qs.filter(assigned_to_id=assigned_to)

        # Sorting support
        sort_by = request.query_params.get("sort_by", "created_at")
        sort_order = request.query_params.get("sort_order", "desc")

        valid_sort_fields = {"status", "title", "deadline", "created_at"}
        if sort_by in valid_sort_fields:
            order_prefix = "-" if sort_order == "desc" else ""
            qs = qs.order_by(f"{order_prefix}{sort_by}")

        return Response(SupportTaskSerializer(qs, many=True).data)

    @extend_schema(request=SupportTaskSerializer, responses=SupportTaskSerializer)
    def post(self, request):
        serializer = SupportTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save(created_by=request.user)
        return Response(SupportTaskSerializer(task).data, status=status.HTTP_201_CREATED)


class SupportTaskDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes = _PERMS

    def _get_task(self, pk):
        try:
            return SupportTask.objects.prefetch_related("actions").get(pk=pk)
        except SupportTask.DoesNotExist:
            return None

    @extend_schema(responses=SupportTaskSerializer)
    def get(self, request, pk):
        task = self._get_task(pk)
        if task is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(SupportTaskSerializer(task).data)

    @extend_schema(request=SupportTaskSerializer, responses=SupportTaskSerializer)
    def patch(self, request, pk):
        task = self._get_task(pk)
        if task is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = SupportTaskSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(SupportTaskSerializer(task).data)


class SupportTaskActionUpdateView(APIView):
    """Update dynamic parameters of a pending action (e.g. edit AI-generated draft)."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    @extend_schema(request=SupportTaskActionSerializer, responses=SupportTaskActionSerializer)
    def patch(self, request, task_pk, action_pk):
        try:
            action = SupportTaskAction.objects.get(pk=action_pk, task_id=task_pk)
        except SupportTaskAction.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if action.status != SupportTaskAction.Status.PENDING:
            return Response(
                {"error": "Cannot edit a non-pending action"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_params = request.data.get("parameters")
        if new_params is not None:
            if not action.was_edited:
                action.original_parameters = action.parameters
            action.parameters = new_params
            action.save()

        return Response(SupportTaskActionSerializer(action).data)


class SupportTaskActionApproveView(APIView):
    """Approve an action — executes the underlying function after human confirmation."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def post(self, request, task_pk, action_pk):
        try:
            action = SupportTaskAction.objects.get(pk=action_pk, task_id=task_pk)
        except SupportTaskAction.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if action.status != SupportTaskAction.Status.PENDING:
            return Response(
                {"error": "Action already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            execute(action)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        action.status = SupportTaskAction.Status.APPROVED
        action.approved_by = request.user
        action.approved_at = timezone.now()
        action.save()

        # For profile review actions with "dismiss" decision, close the parent task
        decision = action.parameters.get("decision")
        if decision == "dismiss" and action.action_type in (
            "profile_action_suspicious_profile",
            "profile_action_too_empty_profile",
        ):
            task = action.task
            task.status = SupportTask.Status.FINISHED
            task.save(update_fields=["status"])

        return Response(SupportTaskActionSerializer(action).data)


class SupportTaskActionSkipView(APIView):
    """Skip an action without executing it."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def post(self, request, task_pk, action_pk):
        try:
            action = SupportTaskAction.objects.get(pk=action_pk, task_id=task_pk)
        except SupportTaskAction.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if action.status != SupportTaskAction.Status.PENDING:
            return Response(
                {"error": "Action already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action.status = SupportTaskAction.Status.SKIPPED
        action.approved_by = request.user
        action.approved_at = timezone.now()
        action.save()

        return Response(SupportTaskActionSerializer(action).data)


class StaffUsersView(APIView):
    """Returns all staff users for task assignment."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def get(self, request):
        users = User.objects.filter(is_staff=True).values("id", "email", "first_name", "last_name")
        return Response(list(users))


class SupportTaskReminderListView(APIView):
    """List and create reminders for a specific task."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def _get_task(self, pk):
        try:
            return SupportTask.objects.get(pk=pk)
        except SupportTask.DoesNotExist:
            return None

    @extend_schema(responses=SupportTaskReminderSerializer(many=True))
    def get(self, request, task_pk):
        task = self._get_task(task_pk)
        if task is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        qs = SupportTaskReminder.objects.filter(task=task).prefetch_related("additional_recipients")
        return Response(SupportTaskReminderSerializer(qs, many=True).data)

    @extend_schema(request=SupportTaskReminderSerializer, responses=SupportTaskReminderSerializer)
    def post(self, request, task_pk):
        task = self._get_task(task_pk)
        if task is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = SupportTaskReminderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reminder = serializer.save(task=task, created_by=request.user)
        return Response(
            SupportTaskReminderSerializer(reminder).data,
            status=status.HTTP_201_CREATED,
        )


class SupportTaskReminderDetailView(APIView):
    """Cancel a specific reminder."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def delete(self, request, task_pk, pk):
        try:
            reminder = SupportTaskReminder.objects.get(pk=pk, task_id=task_pk)
        except SupportTaskReminder.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if reminder.status != SupportTaskReminder.Status.PENDING:
            return Response(
                {"error": "Only pending reminders can be cancelled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reminder.status = SupportTaskReminder.Status.CANCELLED
        reminder.save(update_fields=["status"])
        return Response(SupportTaskReminderSerializer(reminder).data)


api_urls = [
    path("api/admin_tasks/", SupportTaskListView.as_view()),
    path("api/admin_tasks/staff_users/", StaffUsersView.as_view()),
    path("api/admin_tasks/<int:pk>/", SupportTaskDetailView.as_view()),
    path(
        "api/admin_tasks/<int:task_pk>/actions/<int:action_pk>/",
        SupportTaskActionUpdateView.as_view(),
    ),
    path(
        "api/admin_tasks/<int:task_pk>/actions/<int:action_pk>/approve/",
        SupportTaskActionApproveView.as_view(),
    ),
    path(
        "api/admin_tasks/<int:task_pk>/actions/<int:action_pk>/skip/",
        SupportTaskActionSkipView.as_view(),
    ),
    path(
        "api/admin_tasks/<int:task_pk>/reminders/",
        SupportTaskReminderListView.as_view(),
    ),
    path(
        "api/admin_tasks/<int:task_pk>/reminders/<int:pk>/",
        SupportTaskReminderDetailView.as_view(),
    ),
]
