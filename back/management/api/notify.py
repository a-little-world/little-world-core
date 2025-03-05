from dataclasses import dataclass, field
from typing import Optional

from django.core.paginator import Paginator
from django.urls import path
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import authentication, permissions, serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer

from management.helpers import DetailedPagination
from management.models.notifications import Notification, SelfNotificationSerializer
from management.models.user import User


@dataclass
class NotificationGetPaginatedParams:
    page: int
    page_size: int

    filter: Notification.NotificationState | Notification.NotificationStateFilterAll


class NotificationGetPaginatedSerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1, required=False)
    page_size = serializers.IntegerField(min_value=1, default=20, required=False)
    filter = serializers.CharField(default=Notification.NotificationState.UNREAD, required=False)

    def create(self, validated_data):
        return NotificationGetPaginatedParams(**validated_data)


@dataclass
class NotificationGetParams:
    id: int


class NotificationGetSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)

    def create(self, validated_data):
        return NotificationGetParams(**validated_data)


@dataclass
class NotificationUpdateParams:
    state: Notification.NotificationState


class NotificationUpdateSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=Notification.NotificationState.choices, required=True)

    def create(self, validated_data):
        return NotificationUpdateParams(**validated_data)


class PaginatedNotificationResponse(DetailedPagination):
    items = SelfNotificationSerializer(many=True)


@extend_schema(
    description="Retrieve notifications",
    request=NotificationGetPaginatedSerializer(many=False),
    responses={
        200: PaginatedNotificationResponse,
    },
    parameters=[
        OpenApiParameter(
            name="page",
            required=False,
            type=int,
            default=1,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="page_size",
            required=False,
            type=int,
            default=20,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="filter",
            required=False,
            default=Notification.NotificationState.UNREAD,
            type=Notification.NotificationState | Notification.NotificationStateFilterAll,
            location=OpenApiParameter.QUERY,
        ),
    ],
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([authentication.SessionAuthentication])
def get_notifications(request):
    serializer: NotificationGetPaginatedSerializer = NotificationGetPaginatedSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    params: NotificationGetPaginatedParams = serializer.save()

    assert isinstance(request.user, User)

    notifications_user = request.user.get_notifications(state=params.filter)
    paginator = DetailedPagination()
    pages = paginator.get_paginated_response(paginator.paginate_queryset(notifications_user, request)).data
    pages["results"] = SelfNotificationSerializer(pages["results"], many=True).data
    return Response(pages)


@extend_schema(
    description="Retrieve a single notification",
    request=NotificationGetPaginatedSerializer(many=False),
    parameters=[
        OpenApiParameter(
            name="id",
            required=True,
            type=int,
            location=OpenApiParameter.PATH,
        ),
    ],
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([authentication.SessionAuthentication])
def get_notification(request, id):
    assert isinstance(request.user, User)

    notification = Notification.objects.get(id=id)
    return Response(SelfNotificationSerializer(notification).data)


@extend_schema(
    description="Update a notification",
    request=NotificationUpdateSerializer(many=False),
    parameters=[
        OpenApiParameter(
            name="id",
            required=True,
            type=int,
            location=OpenApiParameter.PATH,
        ),
    ],
)
@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([authentication.SessionAuthentication])
def update_notification(request, id):
    serializer: NotificationUpdateSerializer = NotificationUpdateSerializer(data={"id": id, **request.data})
    serializer.is_valid(raise_exception=True)
    params: NotificationUpdateParams = serializer.save()

    notification = Notification.objects.get(id=id)
    notification.update_state(params.state)

    return Response(SelfNotificationSerializer(notification).data)


@extend_schema(
    description="Delete a notification",
    request=NotificationGetSerializer(many=False),
    parameters=[
        OpenApiParameter(
            name="id",
            required=True,
            type=int,
            location=OpenApiParameter.PATH,
        ),
    ],
)
@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([authentication.SessionAuthentication])
def delete_notification(request, id):
    notification = Notification.objects.get(id=id)
    assert request.user == notification.user

    notification.update_state(Notification.NotificationState.DELETED)
    return Response(status=200)


api_routes = [
    path("api/notifications", get_notifications),
    path("api/notifications/<int:id>", get_notification),
    path("api/notifications/<int:id>/delete", delete_notification),
    path("api/notifications/<int:id>/update", update_notification),
]
