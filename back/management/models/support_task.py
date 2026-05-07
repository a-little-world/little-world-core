from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class SupportTask(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", _("New")
        IN_PROGRESS = "IN_PROGRESS", _("In Progress")
        COMPLETED = "COMPLETED", _("Completed")

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)

    assigned_to = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="assigned_support_task",
    )
    created_by = models.ForeignKey(
        "management.User",
        on_delete=models.DO_NOTHING,
        related_name="created_support_task",
    )
    related_user = models.ForeignKey(
        "management.User",
        on_delete=models.DO_NOTHING,
        related_name="related_support_task",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateField(null=True, blank=True)

    action: "SupportTaskAction"

    @classmethod
    def create_of_type(cls, task_type: str, *, static_parameters: dict, parameters: dict, **kwargs) -> "SupportTask":
        """Atomically create a task of a registered type with the corresponding action."""
        from management.actions.registry import get_action_definition, get_task_definition, registered_task_types

        if task_type not in registered_task_types():
            raise ValueError(f"Unknown task type: '{task_type}'")

        task_definition = get_task_definition(task_type)
        assert task_definition
        action_definition = get_action_definition(task_definition.action_type)
        assert action_definition

        try:
            action_definition.static_schema(**static_parameters)
        except TypeError as e:
            raise ValueError(f"Invalid static_parameters: {e}")
        try:
            action_definition.param_schema(**parameters)
        except TypeError as e:
            raise ValueError(f"Invalid parameters: {e}")

        with transaction.atomic():
            task = cls.objects.create(
                title=task_definition.task_title(static_parameters),
                description=task_definition.task_description(static_parameters),
                **kwargs,
            )
            SupportTaskAction.objects.create(
                task=task,
                action_type=task_definition.action_type,
                static_parameters=static_parameters,
                parameters=parameters,
            )
        return task

    def can_complete(self) -> bool:
        return self.action.status != SupportTaskAction.Status.OPEN

    def complete(self) -> None:
        if not self.can_complete():
            raise ValueError("Cannot complete task with open action")
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now().date()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SupportTask({self.pk}): {self.title}"


class SupportTaskAction(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", _("Open")
        CANCELLED = "CANCELLED", _("Cancelled")
        EXECUTED = "EXECUTED", _("Executed")

    task = models.OneToOneField(SupportTask, on_delete=models.CASCADE, related_name="action")

    # Identifies the handler in the registry — fixed at creation, never editable.
    # Validated against the task type registry in SupportTask.create_of_type().
    action_type = models.CharField(max_length=100)

    # Context params set at creation — fixed, not editable by admin (e.g. help_message_id, user_id)
    static_parameters = models.JSONField(default=dict)

    # Dynamic params — initially system/AI-generated, editable by admin before execution
    parameters = models.JSONField(default=dict)

    # Populated only when admin edits `parameters` for the first time, storing the originals.
    # Empty dict means no edits were made.
    original_parameters = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    reviewed_by = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="approved_task_actions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    @property
    def was_edited(self) -> bool:
        return bool(self.original_parameters)

    def resolve(self, new_status: "SupportTaskAction.Status", reviewed_by) -> None:
        if self.status != self.Status.OPEN:
            raise ValueError("Action is already resolved.")
        if new_status not in (self.Status.EXECUTED, self.Status.CANCELLED):
            raise ValueError(f"Invalid resolution status: '{new_status}'.")
        self.status = new_status
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        self.task.complete()

    def __str__(self):
        return f"SupportTaskAction({self.pk}): {self.action_type} [{self.status}]"


class SupportTaskActionSerializer(serializers.ModelSerializer):
    was_edited = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupportTaskAction
        fields = [
            "id",
            "action_type",
            "static_parameters",
            "parameters",
            "original_parameters",
            "was_edited",
            "status",
            "reviewed_by_id",
            "reviewed_at",
        ]
        read_only_fields = [
            "action_type",
            "static_parameters",
            "original_parameters",
            "was_edited",
            "status",
            "reviewed_by_id",
            "reviewed_at",
        ]


class SupportTaskSerializer(serializers.ModelSerializer):
    action = SupportTaskActionSerializer(read_only=True)

    class Meta:
        model = SupportTask
        fields = [
            "id",
            "title",
            "description",
            "status",
            "assigned_to_id",
            "created_by_id",
            "related_user_id",
            "created_at",
            "updated_at",
            "action",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "created_by_id",
        ]
