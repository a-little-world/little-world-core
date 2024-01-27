from channels.security.websocket import AllowedHostsOriginValidator
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "back.settings")
django_asgi_app = get_asgi_application()


def get_urls_patterns():
    from chat_old.django_private_chat2 import urls
    from chat.consumers.core import CoreConsumer

    return [*urls.websocket_urlpatterns, re_path(
        rf'^api/core/ws$', CoreConsumer.as_asgi())]


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(
        URLRouter(get_urls_patterns())
    )),
})
