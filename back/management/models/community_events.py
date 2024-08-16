from django.db import models
from back.utils import get_options_serializer
from rest_framework import serializers
from translations import get_translation
from django.utils.deconstruct import deconstructible
from uuid import uuid4
import os


@deconstructible
class PathRenameCommunityEvent(object):
    def __init__(self, path):
        self.sub_path = path

    def __call__(self, instance, filename):
        ext = filename.split(".")[-1]

        if instance.pk:
            filename = "{}.{}".format(instance.pk, ext)
        else:
            filename = "{}.{}".format(uuid4().hex, ext)
        return os.path.join(self.sub_path, filename)


class CommunityEvent(models.Model):
    """
    DB model for comunity events
    """

    title = models.CharField(max_length=255, null=False, blank=False)
    description = models.CharField(max_length=255, null=False, blank=False)

    time = models.DateTimeField(null=False, blank=False)
    end_time = models.DateTimeField(null=True, blank=True)

    link = models.CharField(default="", max_length=255)

    class EventFrequencyChoices(models.TextChoices):
        MONTHLY = "monthly", get_translation("model.community_event.frequency.monthly")
        WEEKLY = "weekly", get_translation("model.community_event.frequency.weekly")
        ONCE = "once", get_translation("model.community_event.frequency.once")

    frequency = models.CharField(
        max_length=255,
        choices=EventFrequencyChoices.choices,
        default=EventFrequencyChoices.ONCE,
    )

    image = models.ImageField(upload_to=PathRenameCommunityEvent("community_events_pics/"), blank=True)
    active = models.BooleanField(default=False)
    """
    If the event is active, if you don't want users to see this event just set it to inactive!
    """

    @classmethod
    def get_all_active_events(cls, order_by="time"):
        return cls.objects.all().filter(active=True).order_by(order_by)


class CommunityEventSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    def get_options(self, obj):
        return get_options_serializer(self, obj)

    class Meta:
        model = CommunityEvent
        fields = [
            "title",
            "description",
            "time",
            "end_time",
            "frequency",
            "options",
            "link",
            "image",
            "id",
        ]
