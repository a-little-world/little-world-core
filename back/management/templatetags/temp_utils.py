from django import template
from django.conf import settings
register = template.Library()


@register.simple_tag
def create_dict(str_dict):
    return eval(str_dict)


@register.simple_tag
def get_base_url():
    return settings.BASE_URL
