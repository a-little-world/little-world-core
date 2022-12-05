from django.db import models
from django.utils.translation import pgettext_lazy
from back.utils import get_options_serializer
from rest_framework import serializers


class CommunityEvent(models.Model):
    """
    DB model for comunity events 
    """

    title = models.CharField(max_length=255, null=False, blank=False)
    description = models.CharField(max_length=255, null=False, blank=False)

    time = models.DateTimeField(null=False, blank=False)

    link = models.CharField(default="", max_length=255)

    class EventFrequencyChoices(models.TextChoices):
        WEEKLY = "weekly", pgettext_lazy(
            'model.community-event.frequency-weekly', "Weekly")
        ONCE = "once", pgettext_lazy(
            'model.community-event.frequency-once', "Once")

    frequency = models.CharField(
        max_length=255, choices=EventFrequencyChoices.choices,
        default=EventFrequencyChoices.ONCE)

    active = models.BooleanField(default=False)
    """
    If the event is active, if you don't want users to see this event just set it to inactive!
    """

    @classmethod
    def get_all_active_events(cls):
        return cls.objects.all().filter(active=True)


class CommunityEventSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    def get_options(self, obj):
        return get_options_serializer(self, obj)

    class Meta:
        model = CommunityEvent
        fields = ['title', 'description', 'time', 'frequency', 'options']
