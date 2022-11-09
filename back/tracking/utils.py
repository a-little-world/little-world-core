from functools import partial, wraps


def _dispath_event_tracking(f, caller="anonymous", event_name="", tags=[]):

    @wraps(f)
    def run(*args, **kwargs):
        return f(*args, **kwargs)
    return run


def track_event(**kwargs):
    return partial(_dispath_event_tracking, **kwargs)
