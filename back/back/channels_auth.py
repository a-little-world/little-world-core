from urllib.parse import parse_qs

from channels.auth import get_user as channels_get_user
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.sessions import CookieMiddleware, SessionMiddleware
from django.contrib.auth.models import AnonymousUser

def MultiAuthMiddlewareStack(inner):
    # TODO re-add JWT-based auth here
    return CookieMiddleware(SessionMiddleware(inner)) 