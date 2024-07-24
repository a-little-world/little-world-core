from django import template
from django.conf import settings
from django.utils.safestring import mark_safe
from translations import get_translation_catalog
from management.api.options import get_options_dict
from django.conf import settings
import json
register = template.Library()

@register.simple_tag
def get_base_url():
    return settings.EMAIL_STATIC_URL