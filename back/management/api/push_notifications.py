from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import authentication, serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from management.models.user import MobileDevice


@dataclass
class PushNotificationRegistrationParams:
    install_id: str
    token: str
    platform: str | None = None
    model_name: str | None = None


class PushNotificationRegistrationSerializer(serializers.Serializer):
    install_id = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    platform = serializers.CharField(required=False)
    model_name = serializers.CharField(required=False)

    def create(self, validated_data):
        return PushNotificationRegistrationParams(**validated_data)


def get_firebase_service_worker(request):
    code = render_to_string("firebase-worker.js", context=settings.FIREBASE_CLIENT_CONFIG)

    return HttpResponse(code, content_type="application/javascript", charset="utf-8")


@extend_schema(
    description="Register a new push notification device token",
    request=PushNotificationRegistrationParams,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([authentication.SessionAuthentication, JWTAuthentication])
def register_push_notifications_token(request):
    serializer: PushNotificationRegistrationSerializer = PushNotificationRegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    params: PushNotificationRegistrationParams = serializer.save()

    install_id = params.install_id
    token = params.token
    platform = params.platform
    model_name = params.model_name
    user = request.user

    def apply_updates(device, update_install_id=False, update_registration_id=False):
        if update_install_id:
            device.install_id = install_id

        if update_registration_id:
            device.registration_id = token
        device.user = user
        device.platform = platform
        device.model_name = model_name
        device.active = True
        device.cloud_message_type = "FCM"
        device.save()

    device = MobileDevice.objects.filter(registration_id=token).first()

    if device:
        apply_updates(device, update_install_id=True)
        return Response(status=200)

    device = MobileDevice.objects.filter(install_id=install_id).first()

    if device:
        apply_updates(device, update_registration_id=True)
        return Response(status=200)

    MobileDevice.objects.create(
        registration_id=token,
        install_id=install_id,
        user=user,
        platform=platform,
        model_name=model_name,
        active=True,
        cloud_message_type="FCM",
    )

    return Response(status=200)


@extend_schema(
    description="Unregister a push notification device token",
    request=PushNotificationRegistrationParams,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([authentication.SessionAuthentication, JWTAuthentication])
def un_register_push_notifications_token(request):
    serializer: PushNotificationRegistrationSerializer = PushNotificationRegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    params: PushNotificationRegistrationParams = serializer.save()

    install_id = params.install_id
    token = params.token

    with transaction.atomic():
        MobileDevice.objects.filter(Q(install_id=install_id) | Q(registration_id=token)).update(active=False)

    return Response(status=200)


api_urls = [
    path("firebase-messaging-sw.js", get_firebase_service_worker),
    path("api/push_notifications/register", register_push_notifications_token),
    path("api/push_notifications/unregister", un_register_push_notifications_token),
]
