from django import template
from django.utils.safestring import mark_safe

register = template.Library()


TAG = """<script type='text/javascript' async src='/api/auto-reload/reload-script.js'></script>"""

@register.simple_tag
def get_reload_script_tag():
    from django.conf import settings
    if not settings.USE_AUTO_RELOAD:
        return ""
    return mark_safe(TAG)
