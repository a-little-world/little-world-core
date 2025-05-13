from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from firebase_admin import messaging
from push_notifications.models import GCMDevice
from rest_framework import authentication, serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.helpers import IsAdminOrMatchingUser
from management.models.user import User


@dataclass
class PushNotificationTokenParams:
    token: str


class PushNotificationTokenSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)

    def create(self, validated_data):
        return PushNotificationTokenParams(**validated_data)


@dataclass
class PushNotificationParams:
    user: int
    headline: str
    title: str
    description: str


class PushNotificationSerializer(serializers.Serializer):
    user = serializers.CharField(required=True)
    headline = serializers.CharField(required=True)
    title = serializers.CharField(required=True)
    description = serializers.CharField(required=True)

    def create(self, validated_data):
        return PushNotificationParams(**validated_data)


def get_firebase_service_worker(request):
    code = render_to_string("firebase-worker.js", context=settings.FIREBASE_CLIENT_CONFIG)

    return HttpResponse(code, content_type="application/javascript", charset="utf-8")


@extend_schema(
    description="Register a new push notification device token",
    request=PushNotificationTokenParams,
)
@api_view(["POST"])
@authentication_classes([authentication.SessionAuthentication])
def register_push_notifications_token(request):
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
@authentication_classes([authentication.SessionAuthentication])
def un_register_push_notifications_token(request):
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
    description="Send a push notification to the user",
    request=PushNotificationParams,
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([authentication.SessionAuthentication])
def send_push_notification(request):
    serializer: PushNotificationSerializer = PushNotificationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    params: PushNotificationParams = serializer.save()

    user = User.objects.get(id=params.user)
    devices = GCMDevice.objects.filter(user=user)

    message = messaging.Message(
        data={
            "headline": params.headline,
            "title": params.title,
            "description": params.description,
            "timestamp": str(timezone.now()),
        },
    )

    devices.send_message(message)
    return Response(status=200)


@extend_schema(
    description="Send a test push notification to the device of the user with the provided token",
    request=PushNotificationTokenParams,
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([authentication.SessionAuthentication])
def send_test_push_notification(request):
    serializer: PushNotificationTokenSerializer = PushNotificationTokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    params: PushNotificationTokenParams = serializer.save()

    fcm_device = GCMDevice.objects.get(registration_id=params.token, user=request.user)

    message = messaging.Message(
        data={
            "headline": "Test Headline",
            "title": "Test Title",
            "description": "Test Description",
            "timestamp": str(timezone.now()),
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
    path("api/push_notifications/send_test", send_test_push_notification),
]
