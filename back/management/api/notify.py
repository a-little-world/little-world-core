from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from typing import Optional
from rest_framework import authentication, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from dataclasses import dataclass, field
from rest_framework import serializers
from django.core.paginator import Paginator
from management.models.notifications import Notification, SelfNotificationSerializer
from management.models.user import User


@dataclass
class NotificationApiParams:
    page: int = 1
    paginate_by: int = 20
    options: bool = False


class NotificationApiSerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=False)
    paginate_by = serializers.IntegerField(min_value=1, required=False)
    options = serializers.BooleanField(required=False)

    def create(self, validated_data):
        return NotificationApiParams(**validated_data)  # type: ignore


class NotificationGetApi(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="Retrive notifications",
        request=NotificationApiSerializer(many=False),
        parameters=[
            OpenApiParameter(name="page", description="default: 1", required=False, type=str, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="paginate_by", description="default: 20", required=False, type=str, location=OpenApiParameter.QUERY),
        ],
    )
    def get(self, request):
        serializer = NotificationApiSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()
        assert isinstance(request.user, User)
        notifications_user = request.user.get_notifications()
        paged_notificatons = Paginator(notifications_user, params.paginate_by).page(params.page)

        # TODO: we could allow admins to use the raw NotificationsSerializer
        return Response([SelfNotificationSerializer(p).data for p in paged_notificatons])


@dataclass
class NotificationActionParams(NotificationApiParams):
    hash: "list[str]" = field(default_factory=list)
    action: Optional[str] = None


class NotificationActionSerializer(NotificationApiSerializer):
    hash = serializers.ListField(required=True)
    action = serializers.CharField(required=True)

    def create(self, validated_data):
        return NotificationActionParams(**validated_data)  # type: ignore


actions = ["read", "archive"]


class NotificationActionApi(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="action", description="one of: " + ", ".join([f"'{a}'" for a in actions]), required=True, type=str, location="path"),
        ],
        request=inline_serializer(
            name="hash",
            fields={
                "hash": serializers.ListSerializer(child=serializers.CharField()),
            },
        ),
    )
    def post(self, request, **kwargs):
        """
        this expects some low profile update action like e.g.:  'read', 'archive'
        -> ntfy/read hash=XXXX
        """
        serializer = NotificationActionSerializer(data={**request.data, "action": kwargs.get("action", None)})  # type: ignore
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        assert isinstance(request.user, User)

        usr_notifications = Notification.objects.filter(user=request.user)

        for notification_hash in params.hash:
            notification = usr_notifications.filter(hash=notification_hash)
            assert notification.exists()
            notification = notification.first()
            if params.action == "read":
                notification.mark_read()
            elif params.action == "archive":
                notification.mark_archived()
        return Response("Sucessfully performed notification actions")
