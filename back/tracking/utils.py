from functools import partial, wraps
import json
from .models import Event
from django.utils.translation import gettext_lazy as _
from django.http import HttpRequest
from rest_framework.request import Request
from ipware import get_client_ip  # django-ipware

from back.utils import CoolerJson

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


def inline_track_event(
    *args,
    f=None,
    caller="anonymous",
    name="",
    event_type: str = Event.EventTypeChoices.MISC,
    tags=[],
    track_arguments="__all__",
    censor_args=False,
    censor_kwargs=[],
    **kwargs,
):
    _kwargs = {}
    if track_arguments != "__all__":
        for k in kwargs:
            if k in track_arguments and k not in censor_kwargs:
                _kwargs[k] = kwargs[k]
    else:
        _kwargs = kwargs

    metadata = {
        "kwargs": _kwargs,
        "args": args,
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
                    metadata["request_data1"] = dict(a.data)
                    if censor_kwargs:
                        for arg in censor_kwargs:
                            if arg in metadata["request_data1"]:
                                metadata["request_data1"].pop(arg)
                except:
                    metadata["msg"].append(
                        _("request.data 1 not existing"))

                try:
                    metadata["request_data2"] = {**a.POST, **a.GET}
                    if censor_kwargs:
                        for arg in censor_kwargs:
                            if arg in metadata["request_data2"]:
                                metadata["request_data2"].pop(arg)
                except Exception as e:
                    metadata["msg"].append(
                        _("request.data 2 not existing"))

                try:
                    # If the conversion above didn't work maybe it is a http request
                    drf_request = Request(request=a)
                    metadata["request_data3"] = a.data
                    if censor_kwargs:
                        for arg in censor_kwargs:
                            metadata["request_data3"].pop(arg)
                except:
                    metadata["msg"].append(
                        _("couldn't convert to drf request"))

    try:
        _user.is_staff
        if _user.is_anonymous:
            metadata["usr"] = str(_user)
            _user = None
    except:
        metadata["usr"] = str(_user)
        _user = None

    if caller != "anonymous":
        if _user:
            metadata["usr2"] = str(_user)
        try:
            if not caller.is_anonymous:
                _user = caller
        except:
            metadata["usr3"] = str(_user)
    import json

    #metadata = {m: str(v) for m, v in metadata.items()}

    _input = dict(
        # `time` is set automaticly
        tags=tags,
        func=f.__name__ if f else "unknown",
        type=event_type,
        name=name,
        # Adding the default for json.dumps should normaly prevent this from erroring
        # We dump it using our cooler serializer that falls back to strings
        # and handles some other cases where json would error
        metadata=json.loads(json.dumps(metadata, cls=CoolerJson)),
        **({'caller': _user} if _user else {})
    )
    Event.objects.create(**_input)


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
        inline_track_event(
            *args,
            f=f,
            caller=caller,
            name=name,
            event_type=event_type,
            tags=tags,
            track_arguments=track_arguments,
            censor_args=censor_args,
            censor_kwargs=censor_kwargs,
            **kwargs)
        return f(*args, **kwargs)
    return run


def track_event(**kwargs):
    return partial(_dispath_event_tracking, **kwargs)
