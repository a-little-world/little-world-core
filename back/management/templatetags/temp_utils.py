from django import template
from django.conf import settings
import json
from ..api.trans import get_trans_as_tag_catalogue
register = template.Library()


@register.simple_tag
def create_dict(str_dict):
    return eval(str_dict)


@register.simple_tag
def get_base_url():
    return settings.BASE_URL


@register.simple_tag
def get_api_translations(request):
    """
    A helper tag that returns the api trasnlations  
    This can be used by frontends to dynamicly change error translation lanugages without resending requrests
    """
    return json.dumps({
        lang: get_trans_as_tag_catalogue(request, lang) for lang in settings.FRONTEND_LANGS
    })
