from django.core import serializers
from cookie_consent.models import CookieGroup, Cookie
from cookie_consent.util import get_cookie_dict_from_request
import json


def get_cookie_banner_template_data(request) -> dict:
    cookie_state = get_cookie_dict_from_request(request)
    cookie_data = {"cookieGroups": json.dumps(serializers.serialize("json", CookieGroup.objects.all())), "cookieSets": json.dumps(serializers.serialize("json", Cookie.objects.all())), "cookieStateDict": json.dumps(cookie_state)}
    return {"use_cookie_banner": True, "cookie_data": json.dumps(cookie_data)}
