from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.urls import path
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from translations import get_translation

from management.api.app_integrity import _verify_play_integrity_token, get_app_integrity_challenge_cache_key
from management.api.user import get_user_data
from management.integrity.apple import verify_apple_attestation

# --------------- Native Login API ------------------


class NativeAuthAndroidSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)
    integrity_token = serializers.CharField(required=True)
    key_id = serializers.CharField(required=True)


class NativeAuthIosSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)
    key_id = serializers.CharField(max_length=255, required=True)
    attestation_object = serializers.CharField(required=True)


class NativeAuthWebSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)
    bypass_token = serializers.CharField(required=True)


@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
def native_auth_android(request):
    serializer = NativeAuthAndroidSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]
    integrity_token = serializer.validated_data["integrity_token"]
    key_id = serializer.validated_data["key_id"]

    challenge = cache.get(key=get_app_integrity_challenge_cache_key(key_id)).decode("utf-8")

    if not _verify_play_integrity_token(integrity_token, request_hash=challenge):
        return Response({"detail": "Invalid integrity token or request hash"}, status=status.HTTP_400_BAD_REQUEST)

    return native_auth_common_login(email=email.lower(), password=password)


@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
def native_auth_ios(request):
    serializer = NativeAuthIosSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]
    key_id = serializer.validated_data["key_id"]
    attestation_object = serializer.validated_data["attestation_object"]

    challenge = cache.get(key=get_app_integrity_challenge_cache_key(key_id))
    verify_apple_attestation(
        key_id=key_id, challenge_bytes=challenge, attestation_raw=attestation_object, is_prod=settings.IS_PROD
    )

    return native_auth_common_login(email=email.lower(), password=password)


@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
def native_auth_web(request):
    if settings.IS_PROD:
        return Response(
            {"detail": "Invalid integrity token or request hash"}, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    serializer = NativeAuthWebSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]
    bypass_token = serializer.validated_data["bypass_token"]

    bypass_integrity_check = settings.NATIVE_APP_INTEGRITY_ALLOW_BYPASS and (
        bypass_token == settings.NATIVE_APP_INTEGRITY_BYPASS_TOKEN
    )
    if not bypass_integrity_check:
        return Response({"detail": "Invalid integrity check bypass token"}, status=status.HTTP_400_BAD_REQUEST)

    return native_auth_common_login(email=email.lower(), password=password)


def native_auth_common_login(email, password):
    usr = authenticate(username=email.lower(), password=password)
    if usr is None:
        return Response(get_translation("api.login_failed"), status=status.HTTP_400_BAD_REQUEST)

    if usr.is_staff:
        return Response(get_translation("api.login_failed_staff"), status=status.HTTP_400_BAD_REQUEST)

    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(usr)
    refresh["client"] = "native"

    return Response({"token_access": str(refresh.access_token), "token_refresh": str(refresh), **get_user_data(usr)})


# --------------- Native Token Refresh API -----------------


class NativeTokenAndroidRefreshView(TokenRefreshView):
    """
    Allows to re-fesh native token but only if integrity challenged again
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        refresh_raw: str | None = request.data.get("refresh")  # type: ignore[assignment]
        if not refresh_raw:
            return Response({"detail": "Missing refresh token"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_raw)
        except TokenError as exc:  # includes ExpiredSignatureError etc
            raise InvalidToken(str(exc))

        integrity_token = request.data.get("integrity_token")
        key_id = request.data.get("key_id")
        challenge = cache.get(key=get_app_integrity_challenge_cache_key(key_id))

        if not integrity_token or not challenge:
            return Response({"detail": "Missing integrity token or request hash"}, status=status.HTTP_400_BAD_REQUEST)

        if not _verify_play_integrity_token(integrity_token, request_hash=challenge):
            return Response({"detail": "Invalid integrity token or request hash"}, status=status.HTTP_400_BAD_REQUEST)

        client = refresh.get("client")
        if client != "native":
            return Response(
                {"detail": "Refresh token not valid for native client"}, status=status.HTTP_401_UNAUTHORIZED
            )

        response = super().post(request, *args, **kwargs)
        return response


class NativeTokenIosRefreshView(TokenRefreshView):
    """
    Allows to re-fesh native token but only if integrity challenged again
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        refresh_raw: str | None = request.data.get("refresh")  # type: ignore[assignment]
        if not refresh_raw:
            return Response({"detail": "Missing refresh token"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_raw)
        except TokenError as exc:  # includes ExpiredSignatureError etc
            raise InvalidToken(str(exc))

        key_id = request.data.get("key_id")
        attestation_object = request.data.get("attestation_object")

        challenge = cache.get(key=get_app_integrity_challenge_cache_key(key_id))
        verify_apple_attestation(
            key_id=key_id, challenge_bytes=challenge, attestation_raw=attestation_object, is_prod=settings.IS_PROD
        )

        client = refresh.get("client")
        if client != "native":
            return Response(
                {"detail": "Refresh token not valid for native client"}, status=status.HTTP_401_UNAUTHORIZED
            )

        response = super().post(request, *args, **kwargs)
        return response


class NativeTokenWebRefreshView(TokenRefreshView):
    """
    Allows to re-fesh native token but only if integrity challenged again
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        refresh_raw: str | None = request.data.get("refresh")  # type: ignore[assignment]
        if not refresh_raw:
            return Response({"detail": "Missing refresh token"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_raw)
        except TokenError as exc:  # includes ExpiredSignatureError etc
            raise InvalidToken(str(exc))

        if settings.IS_PROD:
            return Response(
                {"detail": "Invalid integrity token or request hash"}, status=status.HTTP_405_METHOD_NOT_ALLOWED
            )

        bypass_token = request.data.get("bypass_token")

        bypass_integrity_check = settings.NATIVE_APP_INTEGRITY_ALLOW_BYPASS and (
            bypass_token == settings.NATIVE_APP_INTEGRITY_BYPASS_TOKEN
        )
        if not bypass_integrity_check:
            return Response({"detail": "Invalid integrity check bypass token"}, status=status.HTTP_400_BAD_REQUEST)

        client = refresh.get("client")
        if client != "native":
            return Response(
                {"detail": "Refresh token not valid for native client"}, status=status.HTTP_401_UNAUTHORIZED
            )

        response = super().post(request, *args, **kwargs)
        return response


api_urls = [
    path("api/user/native-login/android", native_auth_android, name="native_auth_android"),
    path("api/user/native-login/ios", native_auth_ios, name="native_auth_ios"),
    path("api/user/native-login/web", native_auth_web, name="native_auth_web"),
    path("api/token/refresh/android", NativeTokenAndroidRefreshView.as_view(), name="token_refresh_android"),
    path("api/token/refresh/ios", NativeTokenIosRefreshView.as_view(), name="token_refresh_ios"),
    path("api/token/refresh/web", NativeTokenWebRefreshView.as_view(), name="token_refresh_web"),
]
