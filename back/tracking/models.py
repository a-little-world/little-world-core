from django.db import models
from django.utils.translation import gettext as _
from uuid import uuid4
from management.models import User


def _double_uuid():
    return str(uuid4) + "-" + str(uuid4)


class Event(models.Model):
    """
    Tracks an arbitrary event by adding it to a log list. 
    This is sorta fancy more accessible logging
    """
    # TODO: this model should eventually be saved to a diffeerent database than the main database!
    # Currently this creates an extra database call everytime a tracking event is fired
    hash = models.CharField(max_length=255, blank=True,
                            unique=True, default=_double_uuid)  # type: ignore

    class EventTypeChoices(models.IntegerChoices):
        MISC = 0, _("Misc event")
        REQUEST = 1, _("Request event")
        DATABASE = 2, _("Database event")
        ADMIN = 3, _("Admin event")
        """
        A flow event represents an event that happened during the flow of something 
        e.g.: user form was marked finished or matchin state changed!
        """
        FLOW = 4, _("Flow event")
        EMAIL = 5, _("Email event")
        """
        This is reserved for event triggered from the frontend
        this can be triggered with the `api/event/v1/trigger` TODO make this API
        """
        FRONT = 6, _("Frontend event")

    """ Contains a list of custom assighned tags """
    tags = models.JSONField()

    type = models.IntegerField(choices=EventTypeChoices.choices)

    """ 
    Caller user, but optional
    since there can be also events that have no or an anonymous caller
    """
    caller = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True)

    """ Name of the function that called the event """
    func = models.CharField(max_length=255)

    """ The name of the event """
    name = models.CharField(max_length=255)

    time = models.DateTimeField(auto_now_add=True)

    """ 
    A buch of metadata, for some event time we assume more or less specific metadata
    e.g.: 
    request, should have the 'data' meta-key
    models, should have the 'field' tag if the event changed a field
    etc... TODO: be a little more specific
    """
    metadata = models.JSONField()
