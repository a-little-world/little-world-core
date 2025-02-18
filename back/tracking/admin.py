from django.contrib import admin

# Register your models here.
from django.template.defaultfilters import escape
from django.utils.safestring import mark_safe
from management.models.user import User

from .models import Event, GraphModel, Summaries


@admin.register(Summaries)
class SummariesAdmin(admin.ModelAdmin):
    list_display = ("label", "hash", "rate", "time_created", "meta")


@admin.register(GraphModel)
class GraphModels(admin.ModelAdmin):
    list_display = ("slug", "hash", "graph_data", "meta", "time", "type")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("_abr_hash", "name", "type", "user_ref", "time", "tags", "func", "metadata")
    search_fields = ("hash", "name", "type", "tags", "caller__hash", "caller__email")
    list_filter = ("caller",)

    # readonly_fields = ('user_ref',)

    def user_ref(self, obj):
        if obj.caller is not None:
            from django.contrib.admin.templatetags.admin_urls import admin_urlname
            from django.shortcuts import resolve_url

            url = resolve_url(admin_urlname(User._meta, "change"), obj.caller.pk)
            return mark_safe(f'<a href="{url}">{escape(obj.caller.email)}</a>')

        else:
            return mark_safe("no caller")
