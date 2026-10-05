from django.db import models
from translations import get_translation


class EventFrequencyChoices(models.TextChoices):
    MONTHLY = "monthly", get_translation("model.community_event.frequency.monthly")
    WEEKLY = "weekly", get_translation("model.community_event.frequency.weekly")
    FORTNIGHTLY = "fortnightly", get_translation("model.community_event.frequency.fortnightly")
    ONCE = "once", get_translation("model.community_event.frequency.once")
