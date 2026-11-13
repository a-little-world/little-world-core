from back.utils import get_options_serializer
from django.db import models
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from management.helpers import PathRename
from management.models.audience_filters import FILTER_FUNC_MAP, AudienceFilters
from management.models.event_frequency import EventFrequencyChoices


class CommunityEvent(models.Model):
    """
    DB model for comunity events
    """

    title = models.CharField(max_length=255, null=False, blank=False)
    description = models.TextField(null=False, blank=False)
    group_id = models.CharField(max_length=255, null=True, blank=True)

    time = models.DateTimeField(null=False, blank=False)
    end_time = models.DateTimeField(null=True, blank=True)

    link = models.CharField(default="", max_length=255)

    custom_filter = models.CharField(
        default=AudienceFilters.NONE,
        max_length=255,
        choices=AudienceFilters.choices,
    )

    EventFrequencyChoices = EventFrequencyChoices

    frequency = models.CharField(
        max_length=255,
        choices=EventFrequencyChoices.choices,
        default=EventFrequencyChoices.ONCE,
    )

    image = models.ImageField(upload_to=PathRename("community_events_pics/"), blank=True)
    active = models.BooleanField(default=False)
    """
    If the event is active, if you don't want users to see this event just set it to inactive!
    """

    @classmethod
    def get_active_events_for_user(cls, user):
        non_filter_events = cls.objects.all().filter(active=True, custom_filter="none")
        filter_events = cls.objects.all().filter(~Q(custom_filter="none"), active=True)
        extra_events = []
        for event in filter_events:
            filter_func = FILTER_FUNC_MAP.get(event.custom_filter)
            if filter_func and filter_func(user):
                extra_events.append(event.id)
        extra_events_qs = cls.objects.filter(id__in=extra_events)
        events = non_filter_events | extra_events_qs
        return events.exclude(
            frequency=cls.EventFrequencyChoices.ONCE,
            end_time__lt=timezone.now(),
        ).order_by("time", "id")

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
            "group_id",
            "frequency",
            "options",
            "link",
            "image",
            "id",
        ]


class AdminCommunityEventSerializer(serializers.ModelSerializer):
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
            "group_id",
            "frequency",
            "options",
            "link",
            "image",
            "custom_filter",
            "active",
            "id",
        ]
