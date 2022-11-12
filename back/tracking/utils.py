from functools import partial, wraps
from .models import Event
from django.http import HttpRequest


possible_metadata = [
    "request",
    "user",
    "email"
]


def _dispath_event_tracking(f,
                            caller="anonymous",
                            name="",
                            event_type: int = Event.EventTypeChoices.MISC,
                            tags=[],
                            track_arguments=[],
                            censor_args=False,
                            censor_kwargs=[]
                            ):
    """
    Wrap an arbitray function to track 
    you can provide an event type, name, caller and some tags
    the rest of data is collected automaticly.
    It also tries to collect a bunch of meta data if present.
    For sensitive data use censor_kwargs / censor_args
    """

    @wraps(f)
    def run(*args, **kwargs):
        metadata = {
            "kwargs": {arg: kwargs.get(arg) for arg in track_arguments},
            "args": args
        }
        _user = None
        if event_type == Event.EventTypeChoices.MISC \
                or event_type == Event.EventTypeChoices.REQUEST:
            # In both these cases try to get the 'request' object
            for a in args:
                str_type = str(type(a)).lower()
                if "request" in str_type:
                    try:
                        _user = a.user
                    except:
                        pass

        Event.objects.create(
            # `time` is set automaticly
            tags=tags,
            func=f.__name__,
            type=event_type,
            name=name,
            metadata={},
            **({'caller': _user} if _user else {})
        )
        return f(*args, **kwargs)
    return run


def track_event(**kwargs):
    return partial(_dispath_event_tracking, **kwargs)
