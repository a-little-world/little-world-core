from urllib.parse import parse_qs

from channels.auth import AuthMiddleware
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.sessions import CookieMiddleware, SessionMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        user = scope.get("user", AnonymousUser())
        if isinstance(user, AnonymousUser):
            raw_token = self._get_raw_token_from_scope(scope)
            if raw_token:
                jwt_auth = JWTAuthentication()
                try:
                    validated_token = jwt_auth.get_validated_token(raw_token)
                    user = await database_sync_to_async(jwt_auth.get_user)(validated_token)
                    scope["user"] = user
                except Exception:
                    # Leave as AnonymousUser when token is invalid/expired
                    pass

        return await self.inner(scope, receive, send)

    @staticmethod
    def _get_raw_token_from_scope(scope):
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"sec-websocket-protocol")
        if auth_header:
            try:
                value = auth_header.decode()
            except Exception:
                value = ""
            if value.lower().startswith("bearer."):
                return value.split(".", 1)[1].strip()

        # 2) Query string: ?token=... or ?access=...
        query_string = scope.get("query_string", b"")
        if query_string:
            try:
                params = parse_qs(query_string.decode())
            except Exception:
                params = {}
            for key in ("token", "access"):
                if key in params and params[key]:
                    return params[key][0]

        return None


def MultiAuthMiddlewareStack(inner):
    # Order: Cookies -> Session -> Session Auth -> JWT (fills if anonymous)
    return CookieMiddleware(SessionMiddleware(AuthMiddleware(JWTAuthMiddleware(inner))))