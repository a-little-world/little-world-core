from cookie_consent.models import CookieGroup
from cookie_consent.util import (
    accept_cookies,
    decline_cookies,
    dict_to_cookie_str,
    get_cookie_dict_from_request,
    get_cookie_value_from_request,
)
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def get_dynamic_cookie_banner_js(request):
    context = {
        "request": request,
        "hidden_cookie_banner": request.GET.get("hidden", "").lower() == "true",
    }
    code = render_to_string("exporable_cookie_banner_template.js", context)
    return HttpResponse(code, content_type="application/javascript", charset="utf-8")


def _state_from_value(value):
    if value is True:
        return "accepted"
    if value is False:
        return "declined"
    return "unset"


def _serialize_cookie(cookie):
    return {
        "name": cookie.name,
        "description": cookie.description,
        "domain": cookie.domain,
        "path": cookie.path,
    }


def _serialize_groups(request, overrides=None):
    overrides = overrides or {}
    groups = []
    for group in CookieGroup.objects.all():
        if group.is_required:
            state = "accepted"
        elif group.varname in overrides:
            state = _state_from_value(bool(overrides[group.varname]))
        else:
            state = _state_from_value(get_cookie_value_from_request(request, group.varname))

        groups.append(
            {
                "varname": group.varname,
                "name": group.name,
                "description": group.description,
                "is_required": group.is_required,
                "state": state,
                "cookies": [_serialize_cookie(cookie) for cookie in group.cookie_set.all()],
            }
        )
    return groups


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def cookie_settings(request):
    """
    Public read/write API for the cookie settings page.

    GET returns every cookie group with the consent state for the current visitor.
    POST accepts ``{"preferences": {"<varname>": true|false}}`` and records the
    consent using the same machinery as the cookie banner (audit log + consent cookie).
    """
    if request.method == "GET":
        return Response({"groups": _serialize_groups(request)})

    preferences = request.data.get("preferences") or {}
    changed = {}

    response = Response()
    # `accept_cookies`/`decline_cookies` each start from the request cookie value, so
    # keep the request in sync to avoid later groups overwriting earlier decisions.
    cookie_dic = get_cookie_dict_from_request(request)
    for group in CookieGroup.objects.filter(is_required=False):
        if group.varname not in preferences:
            continue

        accepted = bool(preferences[group.varname])
        changed[group.varname] = accepted
        if accepted:
            cookie_dic[group.varname] = group.get_version()
            accept_cookies(request, response, group.varname)
        else:
            cookie_dic[group.varname] = settings.COOKIE_CONSENT_DECLINE
            decline_cookies(request, response, group.varname)
        request.COOKIES[settings.COOKIE_CONSENT_NAME] = dict_to_cookie_str(cookie_dic)

    response.data = {"groups": _serialize_groups(request, overrides=changed)}
    return response
