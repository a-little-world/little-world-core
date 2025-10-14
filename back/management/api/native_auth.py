
import hashlib
import hmac
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional
from django.urls import path
from management.api.user import get_user_data
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Q
from django.dispatch import receiver
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django_rest_passwordreset.signals import reset_password_token_created
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from emails import mails
from emails.mails import PwResetMailParams, get_mail_data_by_name
from rest_framework import authentication, permissions, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from tracking import utils
from tracking.models import Event
from translations import get_translation

from management.controller import UserNotFoundErr, delete_user, get_user, get_user_by_email, get_user_by_hash
from management.authentication import NativeOnlyJWTAuthentication as JWTAuthentication
from django.db.models import Q
from typing import Any, Dict

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from management.api.app_integrity import _verify_play_integrity_token

# --------------- Native Login API ------------------

class NativeAuthApiSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)
    integrity_token = serializers.CharField(required=True)
    request_hash = serializers.CharField(required=True)


@api_view(["POST"])
@permission_classes([])
def native_auth(request):
    serializer = NativeAuthApiSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]
    integrity_token = serializer.validated_data["integrity_token"]
    request_hash = serializer.validated_data["request_hash"]

    if not _verify_play_integrity_token(integrity_token, request_hash):
        return Response({"detail": "Invalid integrity token or request hash"}, status=status.HTTP_400_BAD_REQUEST)

    usr = authenticate(username=email.lower(), password=password)
    if usr is None:
        return Response(get_translation("api.login_failed"), status=status.HTTP_400_BAD_REQUEST)
    
    if usr.is_staff:
        return Response(get_translation("api.login_failed_staff"), status=status.HTTP_400_BAD_REQUEST)

    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(usr)
    refresh["client"] = "native"

    return Response({
        "token_access": str(refresh.access_token),
        "token_refresh": str(refresh),
        **get_user_data(usr)
    })

# --------------- Native Token Refresh API -----------------

class NativeTokenRefreshView(TokenRefreshView):
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
        request_hash = request.data.get("request_hash")
        if not integrity_token or not request_hash:
            return Response({"detail": "Missing integrity token or request hash"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not _verify_play_integrity_token(integrity_token, request_hash):
            return Response({"detail": "Invalid integrity token or request hash"}, status=status.HTTP_400_BAD_REQUEST)

        client = refresh.get("client")
        if client != "native":
            return Response({"detail": "Refresh token not valid for native client"}, status=status.HTTP_401_UNAUTHORIZED)

        response = super().post(request, *args, **kwargs)
        return response

class NativeTokenVerifyView(TokenVerifyView):
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

        integrity_token = request.data.get("integrity_token")
        request_hash = request.data.get("request_hash")
        if not integrity_token or not request_hash:
            return Response({"detail": "Missing integrity token or request hash"}, status=status.HTTP_400_BAD_REQUEST)

        if not _verify_play_integrity_token(integrity_token, request_hash):
            return Response({"detail": "Invalid integrity token or request hash"}, status=status.HTTP_400_BAD_REQUEST)
        
        return super().post(request, *args, **kwargs)


api_urls = [
    path("api/user/native-login", native_auth, name="native_auth"),
    path("api/token/refresh", NativeTokenRefreshView.as_view(), name="token_refresh"),
    path("api/token/verify", NativeTokenVerifyView.as_view(), name="token_verify"),
]