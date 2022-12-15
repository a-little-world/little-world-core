from django import template
from django.conf import settings
import json
register = template.Library()


@register.simple_tag
def create_dict(str_dict):
    return eval(str_dict)


@register.simple_tag
def get_base_url():
    # TODO: this was only meant for the email templates
    # and seems to be fixed vir correcting static path in settings
    # so prop depricate!
    return ""
    # return settings.BASE_URL


@register.simple_tag
def get_cookie_banner_data(request):
    from ..views.cookie_banner_frontend import get_cookie_banner_template_data
    return json.dumps(get_cookie_banner_template_data(request))


@register.simple_tag
def get_base_page_url():
    # to be used in exportable_cookie_banner_template.js
    # TODO: depricate
    return ""  # settings.BASE_URL


@register.simple_tag
def get_api_translations(request):
    from ..api.trans import get_trans_as_tag_catalogue
    """
    A helper tag that returns the api trasnlations  
    This can be used by frontends to dynamicly change error translation lanugages without resending requrests
    """
    return json.dumps({
        lang: get_trans_as_tag_catalogue(request, lang) for lang in settings.FRONTEND_LANGS
    })
