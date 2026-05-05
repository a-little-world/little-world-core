from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from management.models.user import User


class SupportTask(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", _("New")
        IN_PROGRESS = "IN_PROGRESS", _("In Progress")
        FINISHED = "FINISHED", _("Finished")

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)

    assigned_to = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_admin_tasks",
    )
    created_by = models.ForeignKey(
        "management.User",
        on_delete=models.SET_NULL,
        related_name="created_admin_tasks",
    )

    deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Link to any related Django object (HelpMessage, User, Match, etc.)
    # TODO: Also set object_id to null when content_type foreign key is deleted
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")

    # Flexible extra data specific to the task type
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SupportTask({self.id}): {self.title}"


class SupportTaskAction(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        APPROVED = "APPROVED", _("Approved")
        SKIPPED = "SKIPPED", _("Skipped")

    task = models.ForeignKey(SupportTask, on_delete=models.CASCADE, related_name="actions")

    # Identifies the handler in the registry — fixed at creation, never editable
    action_type = models.CharField(max_length=100)

    # Context params set at creation — fixed, not editable by admin (e.g. help_message_id, user_id)
    static_parameters = models.JSONField(default=dict)

    # Dynamic params — initially system/AI-generated, editable by admin before approval
    parameters = models.JSONField(default=dict)

    # Populated only when admin edits `parameters` for the first time, storing the originals.
    # Empty dict means no edits were made.
    original_parameters = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_task_actions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    @property
    def was_edited(self) -> bool:
        """True if an admin has edited the dynamic parameters."""
        return bool(self.original_parameters)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"SupportTaskAction({self.id}): {self.action_type} [{self.status}]"


class SupportTaskReminder(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        TRIGGERED = "TRIGGERED", _("Triggered")
        CANCELLED = "CANCELLED", _("Cancelled")

    task = models.ForeignKey(
        SupportTask,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reminders",
    )
    remind_at = models.DateTimeField()
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_reminders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    notify_push = models.BooleanField(default=False)
    notify_email = models.BooleanField(default=False)
    notify_slack = models.BooleanField(default=False)

    notify_assigned_to = models.BooleanField(default=True)
    additional_recipients = models.ManyToManyField(
        "management.User",
        blank=True,
        related_name="additional_reminder_recipients",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["remind_at"]

    def __str__(self):
        return f"SupportTaskReminder({self.id}) for task {self.task_id} at {self.remind_at}"


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
            "approved_by_id",
            "approved_at",
        ]
        read_only_fields = [
            "action_type",
            "static_parameters",
            "original_parameters",
            "was_edited",
            "status",
            "approved_by_id",
            "approved_at",
        ]


class SupportTaskSerializer(serializers.ModelSerializer):
    actions = SupportTaskActionSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTask
        fields = [
            "id",
            "title",
            "description",
            "status",
            "assigned_to_id",
            "created_by_id",
            "deadline",
            "created_at",
            "updated_at",
            "metadata",
            "content_type_id",
            "object_id",
            "actions",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "created_by_id",
            "content_type_id",
            "object_id",
        ]


class SupportTaskReminderSerializer(serializers.ModelSerializer):
    additional_recipients = serializers.SerializerMethodField()
    additional_recipient_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        write_only=True,
        queryset=User.objects.filter(is_staff=True),
        source="additional_recipients",
        required=False,
    )

    def get_additional_recipients(self, obj):
        return list(obj.additional_recipients.values("id", "email", "first_name", "last_name"))

    def create(self, validated_data):
        recipients = validated_data.pop("additional_recipients", [])
        reminder = SupportTaskReminder.objects.create(**validated_data)
        if recipients:
            reminder.additional_recipients.set(recipients)
        return reminder

    class Meta:
        model = SupportTaskReminder
        fields = [
            "id",
            "remind_at",
            "note",
            "status",
            "created_by_id",
            "notify_push",
            "notify_email",
            "notify_slack",
            "notify_assigned_to",
            "additional_recipients",
            "additional_recipient_ids",
            "created_at",
        ]
        read_only_fields = ["id", "status", "created_by_id", "created_at"]
