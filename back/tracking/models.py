from django.db import models
from django.utils.translation import gettext_lazy as _
from management.models import User
from back import utils


class Event(models.Model):
    """
    Tracks an arbitrary event by adding it to a log list.
    This is sorta fancy more accessible logging
    """
    # TODO: this model should eventually be saved to a diffeerent database than the main database!
    # Currently this creates an extra database call everytime a tracking event is fired
    hash = models.CharField(max_length=255, blank=True,
                            unique=True, default=utils._double_uuid)  # type: ignore

    def _abr_hash(self):
        return self.hash[:8]

    class EventTypeChoices(models.TextChoices):
        MISC = "misc", _("Misc event")
        REQUEST = "request", _("Request event")
        DATABASE = "database", _("Database event")
        ADMIN = "admin", _("Admin event")
        """
        A flow event represents an event that happened during the flow of something
        e.g.: user form was marked finished or matchin state changed!
        """
        FLOW = "flow", _("Flow event")
        EMAIL = "email", _("Email event")
        """
        This is reserved for event triggered from the frontend
        this can be triggered with the `api/event/v1/trigger` TODO make this API
        """
        FRONT = "front", _("Frontend event")

    """ Contains a list of custom assighned tags """
    tags = models.JSONField(null=True, blank=True)

    type = models.CharField(choices=EventTypeChoices.choices,
                            default=EventTypeChoices.MISC,
                            max_length=255)

    """
    Caller user, but optional
    since there can be also events that have no or an anonymous caller
    """
    caller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)

    """ Name of the function that called the event """
    func = models.CharField(max_length=255)

    """ The name of the event """
    name = models.CharField(max_length=255, null=True, blank=True)

    time = models.DateTimeField(auto_now_add=True)

    """
    A buch of metadata, for some event time we assume more or less specific metadata
    e.g.:
    request, should have the 'data' meta-key
    models, should have the 'field' tag if the event changed a field
    etc... TODO: be a little more specific
    """
    metadata = models.JSONField()


class Summaries(models.Model):
    """
    Saves daily / hourly / weekly summaries of events
    e.g.: User logins today user messages sent today
    user registrations today


    We want e.g.:
    - users registered today
    - users verified email today
    - users filled user form today
    - users logged in today
    - users send messages today
    - users had a call together today
    - users total time connected to chat
    - users mean call time today
    - amount messages sent today
    - amount matches created today
    """

    class RateChoices(models.TextChoices):
        HOURLY = 'hourly', _('Hourly')
        DAILY = 'daily', _('Daily')
        WEEKLY = 'weekly', _('Weekly')
        MONTHLY = 'monthly', _('Monthly')

    label = models.CharField(max_length=255, blank=False, null=False)

    slug = models.CharField(max_length=255, blank=False, null=False)

    hash = models.CharField(max_length=255, blank=True,
                            default=utils._double_uuid)

    rate = models.CharField(
        max_length=1000, choices=RateChoices.choices, blank=False)

    time_created = models.DateTimeField(auto_now_add=True)

    meta = models.JSONField()


class GraphModel(models.Model):

    time = models.DateTimeField(auto_now_add=True)

    slug = models.CharField(max_length=255, blank=False, null=False)
    hash = models.CharField(max_length=255, blank=True,
                            default=utils._double_uuid)
    graph_data = models.JSONField(blank=True, null=True)

    meta = models.JSONField(blank=True, null=True)
