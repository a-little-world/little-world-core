from django.db import models
from rest_framework import serializers
from translations import get_translation
from management.models.profile import Profile
from django.db.models import Q

from back.utils import get_options_serializer
from management.helpers import PathRename

def filter__capegemini(user):
    lang_skill_german = list(filter(lambda x: x["lang"] == "german", user.profile.lang_skill))
    german_level = lang_skill_german[0]["level"] if len(lang_skill_german) > 0 else Profile.LanguageSkillChoices.LEVEL_0
    better_than_a1a2 = german_level != Profile.LanguageSkillChoices.LEVEL_0

    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and better_than_a1a2

class CommunityEvent(models.Model):
    """
    DB model for comunity events
    """

    title = models.CharField(max_length=255, null=False, blank=False)
    description = models.CharField(max_length=255, null=False, blank=False)

    time = models.DateTimeField(null=False, blank=False)
    end_time = models.DateTimeField(null=True, blank=True)

    link = models.CharField(default="", max_length=255)
    
    class CustomFilterChoices(models.TextChoices):
        CAPEGEMINI = "capegemini", "capegemini"
        NONE = "none", "None"
    
    custom_filter = models.CharField(default=CustomFilterChoices.NONE, max_length=255, choices=CustomFilterChoices.choices)

    class EventFrequencyChoices(models.TextChoices):
        MONTHLY = "monthly", get_translation("model.community_event.frequency.monthly")
        WEEKLY = "weekly", get_translation("model.community_event.frequency.weekly")
        ONCE = "once", get_translation("model.community_event.frequency.once")

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
            if event.custom_filter == "capegemini":
                if filter__capegemini(user):
                    extra_events.append(event.id)
        extra_events_qs = cls.objects.filter(id__in=extra_events)
        return non_filter_events | extra_events_qs

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
