from actions.registry import execute
from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from models import AdminTask, AdminTaskAction, AdminTaskReminder
from rest_framework import authentication, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from serializers import AdminTaskActionSerializer, AdminTaskReminderSerializer, AdminTaskSerializer

from management.models.user import User

_AUTH = [authentication.SessionAuthentication, authentication.BasicAuthentication]
_PERMS = [permissions.IsAuthenticated]


class AdminTaskListView(APIView):
    authentication_classes = _AUTH
    permission_classes = _PERMS

    @extend_schema(responses=AdminTaskSerializer(many=True))
    def get(self, request):
        qs = AdminTask.objects.prefetch_related("actions").all()

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

        return Response(AdminTaskSerializer(qs, many=True).data)

    @extend_schema(request=AdminTaskSerializer, responses=AdminTaskSerializer)
    def post(self, request):
        serializer = AdminTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save(created_by=request.user)
        return Response(AdminTaskSerializer(task).data, status=status.HTTP_201_CREATED)


class AdminTaskDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes = _PERMS

    def _get_task(self, pk):
        try:
            return AdminTask.objects.prefetch_related("actions").get(pk=pk)
        except AdminTask.DoesNotExist:
            return None

    @extend_schema(responses=AdminTaskSerializer)
    def get(self, request, pk):
        task = self._get_task(pk)
        if task is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(AdminTaskSerializer(task).data)

    @extend_schema(request=AdminTaskSerializer, responses=AdminTaskSerializer)
    def patch(self, request, pk):
        task = self._get_task(pk)
        if task is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminTaskSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AdminTaskSerializer(task).data)


class AdminTaskActionUpdateView(APIView):
    """Update dynamic parameters of a pending action (e.g. edit AI-generated draft)."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    @extend_schema(request=AdminTaskActionSerializer, responses=AdminTaskActionSerializer)
    def patch(self, request, task_pk, action_pk):
        try:
            action = AdminTaskAction.objects.get(pk=action_pk, task_id=task_pk)
        except AdminTaskAction.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if action.status != AdminTaskAction.Status.PENDING:
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

        return Response(AdminTaskActionSerializer(action).data)


class AdminTaskActionApproveView(APIView):
    """Approve an action — executes the underlying function after human confirmation."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def post(self, request, task_pk, action_pk):
        try:
            action = AdminTaskAction.objects.get(pk=action_pk, task_id=task_pk)
        except AdminTaskAction.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if action.status != AdminTaskAction.Status.PENDING:
            return Response(
                {"error": "Action already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            execute(action)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        action.status = AdminTaskAction.Status.APPROVED
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
            task.status = AdminTask.Status.FINISHED
            task.save(update_fields=["status"])

        return Response(AdminTaskActionSerializer(action).data)


class AdminTaskActionSkipView(APIView):
    """Skip an action without executing it."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def post(self, request, task_pk, action_pk):
        try:
            action = AdminTaskAction.objects.get(pk=action_pk, task_id=task_pk)
        except AdminTaskAction.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if action.status != AdminTaskAction.Status.PENDING:
            return Response(
                {"error": "Action already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action.status = AdminTaskAction.Status.SKIPPED
        action.approved_by = request.user
        action.approved_at = timezone.now()
        action.save()

        return Response(AdminTaskActionSerializer(action).data)


class StaffUsersView(APIView):
    """Returns all staff users for task assignment."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def get(self, request):
        users = User.objects.filter(is_staff=True).values("id", "email", "first_name", "last_name")
        return Response(list(users))


class AdminTaskReminderListView(APIView):
    """List and create reminders for a specific task."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def _get_task(self, pk):
        try:
            return AdminTask.objects.get(pk=pk)
        except AdminTask.DoesNotExist:
            return None

    @extend_schema(responses=AdminTaskReminderSerializer(many=True))
    def get(self, request, task_pk):
        task = self._get_task(task_pk)
        if task is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        qs = AdminTaskReminder.objects.filter(task=task).prefetch_related("additional_recipients")
        return Response(AdminTaskReminderSerializer(qs, many=True).data)

    @extend_schema(request=AdminTaskReminderSerializer, responses=AdminTaskReminderSerializer)
    def post(self, request, task_pk):
        task = self._get_task(task_pk)
        if task is None:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminTaskReminderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reminder = serializer.save(task=task, created_by=request.user)
        return Response(
            AdminTaskReminderSerializer(reminder).data,
            status=status.HTTP_201_CREATED,
        )


class AdminTaskReminderDetailView(APIView):
    """Cancel a specific reminder."""

    authentication_classes = _AUTH
    permission_classes = _PERMS

    def delete(self, request, task_pk, pk):
        try:
            reminder = AdminTaskReminder.objects.get(pk=pk, task_id=task_pk)
        except AdminTaskReminder.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if reminder.status != AdminTaskReminder.Status.PENDING:
            return Response(
                {"error": "Only pending reminders can be cancelled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reminder.status = AdminTaskReminder.Status.CANCELLED
        reminder.save(update_fields=["status"])
        return Response(AdminTaskReminderSerializer(reminder).data)


api_urls = [
    path("api/admin_tasks/", AdminTaskListView.as_view()),
    path("api/admin_tasks/staff_users/", StaffUsersView.as_view()),
    path("api/admin_tasks/<int:pk>/", AdminTaskDetailView.as_view()),
    path(
        "api/admin_tasks/<int:task_pk>/actions/<int:action_pk>/",
        AdminTaskActionUpdateView.as_view(),
    ),
    path(
        "api/admin_tasks/<int:task_pk>/actions/<int:action_pk>/approve/",
        AdminTaskActionApproveView.as_view(),
    ),
    path(
        "api/admin_tasks/<int:task_pk>/actions/<int:action_pk>/skip/",
        AdminTaskActionSkipView.as_view(),
    ),
    path(
        "api/admin_tasks/<int:task_pk>/reminders/",
        AdminTaskReminderListView.as_view(),
    ),
    path(
        "api/admin_tasks/<int:task_pk>/reminders/<int:pk>/",
        AdminTaskReminderDetailView.as_view(),
    ),
]
