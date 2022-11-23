from django import template
from management.views.cookie_banner_frontend import get_cookie_banner_template_data

register = template.Library()


@register.simple_tag
def load_cookie_data(request):
    return get_cookie_banner_template_data(request)
