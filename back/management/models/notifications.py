from back import utils
from django.db import models
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .user import User


class Notification(models.Model):
    """ 
    A models for an abitray notification notifications can be read by:
    calling POST api/v1/notification/list (this info is also provided in user data)
    calling POST api/v1/notification/read - mark notification as read
    calling POST api/v1/notification/archive - mark message as 'archived'
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    hash = models.CharField(max_length=100, blank=True,
                            unique=True, default=utils._double_uuid)  # type: ignore

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    time_read = models.DateTimeField(null=True)

    class NotificationState(models.IntegerChoices):
        UNREAD = 0, _("unread")
        READ = 1, _("read")
        ARCHIVED = 2, _("archived")
    state = models.IntegerField(choices=NotificationState.choices,
                                default=NotificationState.UNREAD)

    class NotificationType(models.IntegerChoices):
        NONE = 0, _("none")
        MATCH = 1, _("match")
        MESSAGE = 2, _("message")
    type = models.IntegerField(
        choices=NotificationType.choices, default=NotificationType.NONE)

    title = models.CharField(max_length=255, default=_("title"))
    description = models.TextField(default=_("no-description"))

    meta = models.JSONField(default=dict, blank=True)

    def mark_read(self):
        self.state = self.NotificationState.READ

    def mark_archived(self):
        self.state = self.NotificationState.ARCHIVED


class SelfNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["hash", "type", "state", "title", "description"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
