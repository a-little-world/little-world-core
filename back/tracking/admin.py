from django.contrib import admin
from .models import Event, Summaries

# Register your models here.
from django.template.defaultfilters import escape
from django.urls import reverse
from django.utils.safestring import mark_safe
from management.models.user import User


@admin.register(Summaries)
class SummariesAdmin(admin.ModelAdmin):
    list_display = ('label', 'hash', 'rate', 'time_created', 'meta')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('_abr_hash', 'name', 'type', 'user_ref',
                    'time', 'tags', 'func', 'metadata')
    search_fields = ('hash', 'name', 'type', 'tags',
                     'caller__hash', 'caller__email')
    list_filter = ("caller",)

    #readonly_fields = ('user_ref',)

    def user_ref(self, obj):
        if obj.caller is not None:
            from django.shortcuts import resolve_url
            from django.contrib.admin.templatetags.admin_urls import admin_urlname
            url = resolve_url(admin_urlname(
                User._meta, 'change'), obj.caller.pk)
            return mark_safe(f'<a href="{url}">{escape(obj.caller.email)}</a>')

        else:
            return mark_safe('no caller')
