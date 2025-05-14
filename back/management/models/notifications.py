from uuid import uuid4

from django.db import models
from rest_framework import serializers
from translations import get_translation


class Notification(models.Model):
    """
    A models for an arbitrary notification. Notifications can be read by:
    calling POST api/v1/notification/list (this info is also provided in user data)
    calling POST api/v1/notification/read - mark notification as read
    calling POST api/v1/notification/archive - mark message as 'archived'
    """

    user = models.ForeignKey("management.User", on_delete=models.CASCADE)

    hash = models.CharField(max_length=100, blank=True, unique=True, default=uuid4)  # type: ignore

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    time_read = models.DateTimeField(null=True, blank=True)

    class NotificationState(models.TextChoices):
        UNREAD = "unread", get_translation("notification.state.unread")
        READ = "read", get_translation("notification.state.read")
        ARCHIVED = "archived", get_translation("notification.state.archived")
        DELETED = "deleted", get_translation("notification.state.deleted")

    class NotificationStateFilterAll(models.TextChoices):
        ALL = "all", get_translation("notification.state.all")

    state = models.CharField(choices=NotificationState.choices, default=NotificationState.UNREAD, max_length=255)

    class NotificationType(models.TextChoices):
        NONE = "none", get_translation("notification.type.none")
        MATCH = "match", get_translation("notification.type.match")
        MESSAGE = "message", get_translation("notification.type.message")

    type = models.CharField(choices=NotificationType.choices, default=NotificationType.NONE, max_length=255)

    headline = models.CharField(max_length=255, default=get_translation("notification.headline"), blank=True)
    title = models.CharField(max_length=255, default=get_translation("notification.title"), blank=True)
    description = models.TextField(default=get_translation("notification.no_description"))

    meta = models.JSONField(default=dict, blank=True)

    @classmethod
    def get_unread_notifications(cls, user, order_by="-created_at"):
        return cls.objects.filter(user=user, state=cls.NotificationState.UNREAD).order_by(order_by)

    @classmethod
    def get_read_notifications(cls, user, order_by="-created_at"):
        return cls.objects.filter(user=user, state=cls.NotificationState.READ).order_by(order_by)

    @classmethod
    def get_archived_notifications(cls, user, order_by="-created_at"):
        return cls.objects.filter(user=user, state=cls.NotificationState.ARCHIVED).order_by(order_by)

    def update_state(self, state: NotificationState):
        if state == Notification.NotificationState.READ:
            self.mark_read()
        elif state == Notification.NotificationState.UNREAD:
            self.mark_unread()
        elif state == Notification.NotificationState.ARCHIVED:
            self.archive()
        elif state == Notification.NotificationState.DELETED:
            self.mark_deleted()

    def mark_read(self):
        from datetime import datetime

        self.time_read = datetime.now()
        self.state = self.NotificationState.READ
        self.save()

    def mark_unread(self):
        self.time_read = None
        self.state = self.NotificationState.UNREAD
        self.save()

    def archive(self):
        self.state = self.NotificationState.ARCHIVED
        self.save()

    def mark_deleted(self):
        self.state = self.NotificationState.DELETED
        self.save()


class SelfNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "hash", "type", "state", "title", "description", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
