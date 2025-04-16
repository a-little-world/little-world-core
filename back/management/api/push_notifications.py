from dataclasses import dataclass

from management.helpers import IsAdminOrMatchingUser

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path
from drf_spectacular.utils import extend_schema
from firebase_admin import messaging
from push_notifications.models import GCMDevice
from rest_framework import authentication, permissions, serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from django.conf import settings

from management.helpers.get_base64_env import get_base64_env
from management.models.user import User


@dataclass
class PushNotificationTokenParams:
    token: str


class PushNotificationTokenSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)

    def create(self, validated_data):
        return PushNotificationTokenParams(**validated_data)


def get_firebase_service_worker(request):
    code = render_to_string("firebase-worker.js", context=settings.FIREBASE_CLIENT_CONFIG)

    return HttpResponse(code, content_type="application/javascript", charset="utf-8")


@extend_schema(
    description="Register a new push notification device token",
    request=PushNotificationTokenParams,
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([authentication.SessionAuthentication])
def register_push_notifications_token(request):
    assert isinstance(request.user, User)

    serializer: PushNotificationTokenSerializer = PushNotificationTokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    params: PushNotificationTokenParams = serializer.save()
    with transaction.atomic():
        # ensure device cannot register more than once when calling this method multiple times in fast succession
        GCMDevice.objects.get_or_create(registration_id=params.token, user=request.user)

    return Response(status=200)


@extend_schema(
    description="Unregister a push notification device token",
    request=PushNotificationTokenParams,
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([authentication.SessionAuthentication])
def un_register_push_notifications_token(request):
    assert isinstance(request.user, User)

    serializer: PushNotificationTokenSerializer = PushNotificationTokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    params: PushNotificationTokenParams = serializer.save()
    try:
        GCMDevice.objects.get(registration_id=params.token, user=request.user).delete()
    except ObjectDoesNotExist:
        # ignore if token does not exist or was already deleted
        pass

    return Response(status=200)


@extend_schema(
    description="Send a test push notification to the device of the user with the provided token",
    request=PushNotificationTokenParams,
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([authentication.SessionAuthentication])
def send_push_notification(request):
    assert isinstance(request.user, User)
    serializer: PushNotificationTokenSerializer = PushNotificationTokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    params: PushNotificationTokenParams = serializer.save()

    fcm_device = GCMDevice.objects.get(registration_id=params.token, user=request.user)

    message = messaging.Message(
        data={
            "title": "Test Title",
            "body": "Test Message Body",
        },
        token=params.token,
    )

    fcm_device.send_message(message)
    return Response(status=200)


api_urls = [
    path("firebase-messaging-sw.js", get_firebase_service_worker),
    path("api/push_notifications/register", register_push_notifications_token),
    path("api/push_notifications/unregister", un_register_push_notifications_token),
    path("api/push_notifications/send", send_push_notification),
]
