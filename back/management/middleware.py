from django.utils import translation
from django.template import RequestContext
from django.shortcuts import render
from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware


def responde_404(request):
    response = render(request, '404.html', {})
    response.status_code = 404
    return response


# In development it ok if everybody can see the admin paths
IF_NOT_ADMIN_404_ROUTES = [] if settings.DEBUG else [
    "/admin",
    "/admin_chat",
    "/db",
    "/api/schema"
]


def _is_blocked_route(path):
    for route in IF_NOT_ADMIN_404_ROUTES:
        if path.startswith(route):
            return True
    return False


def _404_if_not_staff(request, get_response):
    if not request.user.is_authenticated or not request.user.is_staff:
        return responde_404(request)
    else:
        return get_response(request)


class AdminPathBlockingMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith("/admin/login"):
            # See what I did here, you can only render the admin login if you add `?opensesame`
            if not settings.DEBUG and not settings.ADMIN_OPEN_KEYPHRASE in request.GET:
                return _404_if_not_staff(request, self.get_response)
        else:
            if _is_blocked_route(path):
                return _404_if_not_staff(request, self.get_response)
        return self.get_response(request)


USE_TAG_HEADER = "HTTP_X_USETAGSONLY"


class OverwriteSessionLangIfAcceptLangHeaderSet:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        We add our own http header that can be used to for usage of **only** translations tags for the frontends!
        """
        if USE_TAG_HEADER in request.META and request.META[USE_TAG_HEADER]:
            with translation.override("tag"):
                return self.get_response(request)
        else:
            return self.get_response(request)
