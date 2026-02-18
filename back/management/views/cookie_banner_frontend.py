import json

from cookie_consent.models import Cookie, CookieGroup
from cookie_consent.util import get_cookie_dict_from_request
from django.core import serializers


def get_cookie_banner_template_data(request, hidden_cookie_banner = False) -> dict:
    cookie_state = get_cookie_dict_from_request(request)
    cookie_data = {
        "cookieGroups": json.dumps(serializers.serialize("json", CookieGroup.objects.all())),
        "cookieSets": json.dumps(serializers.serialize("json", Cookie.objects.all())),
        "cookieStateDict": json.dumps(cookie_state),
        "hiddenCookieBanner": hidden_cookie_banner,
    }

    return {"use_cookie_banner": True, "hidden_cookie_banner": hidden_cookie_banner, "cookie_data": json.dumps(cookie_data)}
