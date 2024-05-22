from django import template
from django.conf import settings
from django.utils.safestring import mark_safe
from translations import get_translation_catalog
from management.api.options import get_options_dict
import json
register = template.Library()


@register.simple_tag
def create_dict(str_dict):
    return eval(str_dict)


@register.simple_tag
def get_base_matomo_script_tag():
    CONTAINER_ID = settings.MATOMO_CONTAINER_ID
    return ("""
var _mtm = window._mtm = window._mtm || [];
_mtm.push({'mtm.startTime': (new Date().getTime()), 'event': 'mtm.Start'});
var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0];
""" + f"""g.async=true; g.src='https://matomo.little-world.com/js/{CONTAINER_ID}.js'; s.parentNode.insertBefore(g,s);
""")

@register.simple_tag
def get_sentry_init_script():
    if not settings.USE_SENTRY:
        return ""
    return mark_safe(f"""
<script
  src="https://js.sentry-cdn.com/{settings.SENTRY_ID}.min.js"
  crossorigin="anonymous"
></script>
""")


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
def get_api_translations():
    """
    A helper tag that returns the api trasnlations  
    This can be used by frontends to dynamicly change error translation lanugages without resending requrests
    """
    return json.dumps(get_translation_catalog())


@register.simple_tag
def get_api_options():
    return json.dumps(get_options_dict())
