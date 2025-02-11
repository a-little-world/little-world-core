from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path


def get_reload_script(request):
    code = render_to_string("reload-script.js", {})
    return HttpResponse(code, content_type="application/javascript", charset="utf-8")


def trigger_reload(request):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "reload",
        {
            "type": "reload",
        },
    )
    return HttpResponse("OK")


urlpatters = [
    path("api/auto-reload/reload-script.js", get_reload_script),
    path("api/auto-reload/trigger-reload", trigger_reload, name="trigger-reload"),
]
