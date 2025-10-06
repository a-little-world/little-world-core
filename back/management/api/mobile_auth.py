from typing import Any, Dict

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView


class NativeTokenRefreshView(TokenRefreshView):
    """
    Refreshes tokens only if the provided refresh token carries client="native".
    Ensures newly issued access tokens keep the same client claim.
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        refresh_raw: str | None = request.data.get("refresh")  # type: ignore[assignment]
        if not refresh_raw:
            return Response({"detail": "Missing refresh token"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_raw)
        except TokenError as exc:  # includes ExpiredSignatureError etc
            raise InvalidToken(str(exc))

        client = refresh.get("client")
        if client != "native":
            return Response({"detail": "Refresh token not valid for native client"}, status=status.HTTP_401_UNAUTHORIZED)

        response = super().post(request, *args, **kwargs)
        return response


class NativeTokenVerifyView(TokenVerifyView):
    """
    Verifies tokens but only accepts tokens carrying client="native" claim.
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        token_raw: str | None = request.data.get("token")  # type: ignore[assignment]
        if not token_raw:
            return Response({"detail": "Missing token"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            untyped = UntypedToken(token_raw)
        except TokenError as exc:
            raise InvalidToken(str(exc))

        client = untyped.get("client")
        if client != "native":
            return Response({"detail": "Token not valid for native client"}, status=status.HTTP_401_UNAUTHORIZED)

        return super().post(request, *args, **kwargs)


