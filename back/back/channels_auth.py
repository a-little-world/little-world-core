from urllib.parse import parse_qs

from channels.auth import get_user as channels_get_user
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.sessions import CookieMiddleware, SessionMiddleware
from django.contrib.auth.models import AnonymousUser

from management.models.multi_token_auth import MultiToken


class MultiTokenOrSessionAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        # Try session-based auth first
        user = None
        try:
            session_user = await channels_get_user(scope)
        except Exception:
            session_user = None
        if getattr(session_user, "is_authenticated", False):
            user = session_user
        else:
            # Fallback to token-based auth
            token = self._get_token_from_scope(scope)
            if token:
                user = await self._get_user_for_token(token)

        scope["user"] = user if user is not None else AnonymousUser()
        return await self.inner(scope, receive, send)

    def _get_token_from_scope(self, scope):
        # WebSocket subprotocols (Sec-WebSocket-Protocol: token.<token>)
        try:
            subprotocols = scope.get("subprotocols", []) or []
            for proto in subprotocols:
                if not proto:
                    continue
                p = proto.strip()
                lower = p.lower()
                if lower.startswith("token.") or lower.startswith("bearer."):
                    return p.split(".", 1)[1]
        except Exception:
            pass

        # Query string (?token=...)
        try:
            raw_qs = scope.get("query_string", b"")
            if raw_qs:
                params = parse_qs(raw_qs.decode())
                values = params.get("token")
                if values and len(values) > 0:
                    return values[0]
        except Exception:
            pass

        # Authorization header (Token/Bearer)
        try:
            for header_name, header_value in scope.get("headers", []):
                if header_name == b"authorization":
                    text = header_value.decode()
                    lower = text.lower()
                    if lower.startswith("token ") or lower.startswith("bearer "):
                        return text.split(" ", 1)[1].strip()
                if header_name == b"sec-websocket-protocol":
                    # Could be comma-separated list
                    raw = header_value.decode()
                    for part in [s.strip() for s in raw.split(",")]:
                        lower = part.lower()
                        if lower.startswith("token.") or lower.startswith("bearer."):
                            return part.split(".", 1)[1]
        except Exception:
            pass

        return None

    @database_sync_to_async
    def _get_user_for_token(self, token):
        try:
            t = MultiToken.objects.select_related("user").get(key=token)
            return t.user
        except MultiToken.DoesNotExist:
            return None


def MultiAuthMiddlewareStack(inner):
    return CookieMiddleware(SessionMiddleware(MultiTokenOrSessionAuthMiddleware(inner))) 