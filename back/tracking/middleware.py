import ast
import contextlib
from django.template import RequestContext
from django.shortcuts import render
from django.conf import settings
from .utils import inline_track_event


"""
We wan't to gather as much data as possible.
But never store any passwords! 
So we have to do some manual censoring
"""
CENSOR_ROUTES = {
    "/register": {
        "search": "any",
        "mode": "k",
        "censor": ["password", "password1", "password2"]
    },
    "/login": {  # Also takes care of /admin/login
        "search": "any",
        "mode": "k",
        "censor": ["password"]
    }
    # TODO: add reset password api here
}


def _should_censor(path):
    for p in CENSOR_ROUTES:
        if CENSOR_ROUTES[p]['search'] == "start":
            if path.startswith(p):
                return CENSOR_ROUTES[p]
        if CENSOR_ROUTES[p]['search'] == "any":
            if p in path:
                return CENSOR_ROUTES[p]
    return None


@contextlib.contextmanager
def _try():
    try:
        yield None
    except:
        pass


class TrackRequestsMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        print(path)
        _kwargs = {}

        with _try():
            _kwargs.update({"GET": request.GET})
        with _try():
            _kwargs.update(**request.POST)
        with _try():
            _kwargs.update(**ast.literal_eval(request.body.decode()))

        censor = _should_censor(path)
        _censor_kwargs = []
        if censor:
            print("About to censor", path)
            _kwargs = {k: _kwargs[k]
                       for k in _kwargs if not k in censor["censor"]}
            _censor_kwargs = censor["censor"]

        inline_track_event(*[request], name="request",
                           tags=["middleware", "general"],
                           caller=request.user,
                           censor_kwargs=_censor_kwargs,
                           ** {
            "path": path,
            **_kwargs
        })
        return self.get_response(request)
