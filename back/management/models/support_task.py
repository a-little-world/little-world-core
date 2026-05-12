from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from management.models.object_history import ObjectHistory, ObjectHistorySerializer

_TRACKED_TASK_FIELDS = ("title", "description", "status", "priority", "assigned_to_id")
_TRACKED_ACTION_FIELDS = ("status", "parameters")


def _history_diffs(obj, tracked_fields, update_fields=None):
    """Return list of (field, old_val, new_val) for fields that changed vs DB state."""
    old = type(obj).objects.get(pk=obj.pk)
    check = tracked_fields if update_fields is None else tuple(f for f in tracked_fields if f in update_fields)
    return [(f, getattr(old, f), getattr(obj, f)) for f in check if getattr(old, f) != getattr(obj, f)]


class SupportTask(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", _("New")
        IN_PROGRESS = "IN_PROGRESS", _("In Progress")
        COMPLETED = "COMPLETED", _("Completed")

    class Priority(models.TextChoices):
        LOW = "LOW", _("Low")
        MEDIUM = "MEDIUM", _("Medium")
        HIGH = "HIGH", _("High")
        URGENT = "URGENT", _("Urgent")

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)

    assigned_to = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="assigned_support_tasks",
    )
    created_by = models.ForeignKey(
        "management.User",
        on_delete=models.DO_NOTHING,
        related_name="created_support_tasks",
    )
    related_user = models.ForeignKey(
        "management.User",
        on_delete=models.DO_NOTHING,
        related_name="related_support_tasks",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateField(null=True, blank=True)

    history = GenericRelation(ObjectHistory)
    action: "SupportTaskAction"

    def save(self, *args, changed_by=None, **kwargs) -> None:
        is_new = not self.pk
        diffs = [] if is_new else _history_diffs(self, _TRACKED_TASK_FIELDS, kwargs.get("update_fields"))
        super().save(*args, **kwargs)
        ct = ContentType.objects.get_for_model(self)
        if is_new:
            ObjectHistory.objects.create(
                content_type=ct, object_id=self.pk, changed_by=changed_by, type=ObjectHistory.Type.CREATE
            )
        elif diffs:
            ObjectHistory.objects.bulk_create(
                [
                    ObjectHistory(
                        content_type=ct,
                        object_id=self.pk,
                        changed_by=changed_by,
                        type=ObjectHistory.Type.UPDATE,
                        field=f,
                        old_value=old,
                        new_value=new,
                    )
                    for f, old, new in diffs
                ]
            )

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
            task = cls(
                title=task_definition.task_title(static_parameters),
                description=task_definition.task_description(static_parameters),
                **kwargs,
            )
            task.save(changed_by=kwargs.get("created_by"))
            action = SupportTaskAction(
                task=task,
                action_type=task_definition.action_type,
                static_parameters=static_parameters,
                parameters=parameters,
            )
            action.save()
        return task

    def can_complete(self) -> bool:
        return self.action.status != SupportTaskAction.Status.OPEN

    def complete(self, changed_by=None) -> None:
        if not self.can_complete():
            raise ValueError("Cannot complete task with open action")
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now().date()
        self.save(update_fields=["status", "completed_at", "updated_at"], changed_by=changed_by)

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

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    reviewed_by = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="approved_task_actions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    history = GenericRelation(ObjectHistory)

    def save(self, *args, changed_by=None, **kwargs) -> None:
        is_new = not self.pk
        diffs = [] if is_new else _history_diffs(self, _TRACKED_ACTION_FIELDS, kwargs.get("update_fields"))
        super().save(*args, **kwargs)
        ct = ContentType.objects.get_for_model(self)
        if is_new:
            ObjectHistory.objects.create(
                content_type=ct, object_id=self.pk, changed_by=changed_by, type=ObjectHistory.Type.CREATE
            )
        elif diffs:
            ObjectHistory.objects.bulk_create(
                [
                    ObjectHistory(
                        content_type=ct,
                        object_id=self.pk,
                        changed_by=changed_by,
                        type=ObjectHistory.Type.UPDATE,
                        field=f,
                        old_value=old,
                        new_value=new,
                    )
                    for f, old, new in diffs
                ]
            )

    def resolve(self, new_status: "SupportTaskAction.Status", reviewed_by) -> None:
        if self.status != self.Status.OPEN:
            raise ValueError("Action is already resolved.")
        if new_status not in (self.Status.EXECUTED, self.Status.CANCELLED):
            raise ValueError(f"Invalid resolution status: '{new_status}'.")
        self.status = new_status
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at"], changed_by=reviewed_by)
        self.task.complete(changed_by=reviewed_by)

    def __str__(self):
        return f"SupportTaskAction({self.pk}): {self.action_type} [{self.status}]"


class SupportTaskActionSerializer(serializers.ModelSerializer):
    history = ObjectHistorySerializer(many=True, read_only=True)

    class Meta:
        model = SupportTaskAction
        fields = [
            "id",
            "action_type",
            "static_parameters",
            "parameters",
            "status",
            "reviewed_by_id",
            "reviewed_at",
            "history",
        ]
        read_only_fields = [
            "action_type",
            "static_parameters",
            "parameters",
            "status",
            "reviewed_by_id",
            "reviewed_at",
        ]


class SupportTaskSerializer(serializers.ModelSerializer):
    action = SupportTaskActionSerializer(read_only=True)
    history = ObjectHistorySerializer(many=True, read_only=True)

    def update(self, instance, validated_data):
        changed_by = validated_data.pop("changed_by", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(changed_by=changed_by)
        return instance

    class Meta:
        model = SupportTask
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "assigned_to_id",
            "created_by_id",
            "related_user_id",
            "created_at",
            "updated_at",
            "action",
            "history",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "created_by_id",
        ]
