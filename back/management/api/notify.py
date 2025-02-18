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
    paginate_by: int

    include_unread: bool
    include_read: bool
    include_archived: bool


class NotificationGetPaginatedSerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1, required=False)
    paginate_by = serializers.IntegerField(min_value=1, default=20, required=False)
    include_unread = serializers.BooleanField(default=True, required=False)
    include_read = serializers.BooleanField(default=False, required=False)
    include_archived = serializers.BooleanField(default=False, required=False)

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


@extend_schema(
    description="Retrieve notifications",
    request=NotificationGetPaginatedSerializer(many=False),
    parameters=[
        OpenApiParameter(
            name="page",
            required=False,
            type=int,
            default=1,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="paginate_by",
            required=False,
            type=int,
            default=20,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="include_unread",
            required=False,
            default=True,
            type=bool,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="include_read",
            required=False,
            default=False,
            type=bool,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="include_archived",
            required=False,
            default=False,
            type=bool,
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

    notifications_user = request.user.get_notifications(
        include_unread=params.include_unread, include_read=params.include_read, include_archived=params.include_archived
    )
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


api_routes = [
    path("api/notifications/", get_notifications),
    path("api/notifications/<int:id>", get_notification),
    path("api/notifications/<int:id>/update", update_notification),
]
