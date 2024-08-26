from channels.security.websocket import AllowedHostsOriginValidator
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "back.settings")
django_asgi_app = get_asgi_application()


def get_urls_patterns():
    from chat.consumers.core import CoreConsumer

    from django.conf import settings

    _urls = [re_path(r"^api/core/ws$", CoreConsumer.as_asgi())]

    if settings.USE_AUTO_RELOAD:
        from tbs_django_auto_reload.consumer import ReloadConsumer

        _urls.append(re_path(r"^ws/reload$", ReloadConsumer.as_asgi()))

    return _urls


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(get_urls_patterns()))),
    }
)
