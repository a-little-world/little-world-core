from functools import partial, wraps
from .models import Event
from django.utils.translation import gettext as _
from django.http import HttpRequest
from rest_framework.request import Request
from ipware import get_client_ip  # django-ipware


possible_metadata = [
    "request",
    "user",
    "email"
]


def _ip_meta(request):
    client_ip, is_routable = get_client_ip(request)
    return {
        "IP": client_ip,
        "public": is_routable
    }


def _dispath_event_tracking(f,
                            caller="anonymous",
                            name="",
                            event_type: int = Event.EventTypeChoices.MISC,
                            tags=[],
                            track_arguments="__all__",
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
        import json
        print(args)
        print(kwargs)
        # TODO: for poduction this should fail silently! 'try'
        _kwargs = {}
        if kwargs != "__all__":
            for k in kwargs:
                if k in track_arguments and k not in censor_kwargs:
                    _kwargs[k] = kwargs[k]
        else:
            _kwargs = kwargs

        metadata = {
            "kwargs": str(_kwargs),
            "args": str(args),
            "msg": [],
        }
        _user = None
        if event_type == Event.EventTypeChoices.MISC \
                or event_type == Event.EventTypeChoices.REQUEST:
            # In both these cases try to get the 'request' object
            for a in args:
                str_type = str(type(a)).lower()
                if "request" in str_type:
                    try:
                        metadata.update(_ip_meta(a))
                    except:
                        metadata["msg"].append(
                            _("tracking: could not determine IP"))
                    try:
                        _user = a.user
                    except:
                        metadata["msg"].append(
                            _("traking: could not deterine user"))

                    try:
                        metadata["request_data1"] = a.data
                    except:
                        metadata["msg"].append(
                            _("request.data not existing"))

                    try:
                        # If the conversion above didn't work maybe it is a http request
                        drf_request = Request(request=a)
                        metadata["request_data2"] = a.data
                    except:
                        metadata["msg"].append(
                            _("couldn't convert to drf request"))

        try:
            _user.is_authenticated()
        except:
            metadata["usr"] = str(_user)
            _user = None
        Event.objects.create(
            # `time` is set automaticly
            tags=tags,
            func=f.__name__,
            type=event_type,
            name=name,
            metadata=metadata,
            **({'caller': _user} if _user else {})
        )
        return f(*args, **kwargs)
    return run


def track_event(**kwargs):
    return partial(_dispath_event_tracking, **kwargs)
