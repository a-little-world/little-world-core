from typing import Optional, Tuple

from django.contrib.auth.models import AnonymousUser
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication as SimpleJWTAuthentication


class NativeOnlyJWTAuthentication(SimpleJWTAuthentication):
    """
    JWT authentication that only accepts tokens explicitly issued for the native app.

    Enforces a custom claim: {"client": "native"} on the access token.
    """

    def authenticate(self, request: Request) -> Optional[Tuple[object, object]]:
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result

        # Do not authenticate anonymous users
        if user is None or isinstance(user, AnonymousUser):
            return None

        client = validated_token.get("client")
        if client != "native":
            return None

        return user, validated_token


def silent(auth_class):
    """Wraps an authentication class so it never raises — returns None on any failure instead."""

    class SilentAuth(auth_class):
        def authenticate(self, request):
            try:
                return super().authenticate(request)
            except Exception:
                return None

    SilentAuth.__name__ = f"Silent{auth_class.__name__}"
    SilentAuth.__qualname__ = f"Silent{auth_class.__qualname__}"
    return SilentAuth
