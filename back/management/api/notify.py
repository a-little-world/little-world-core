from drf_spectacular.utils import extend_schema, OpenApiParameter
from typing import Optional
from rest_framework import authentication, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from dataclasses import dataclass
from rest_framework import serializers
from django.core.paginator import Paginator
from ..models.notifications import Notification
from rest_framework import status
from ..models.user import User


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
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):

        serializer = NotificationApiSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()
        assert isinstance(request.user, User)
        notifications_user = request.user.get_notifications()

        return Response(Paginator(notifications_user, params.paginate_by).page(params.page))


@dataclass
class NotificationActionParams(NotificationApiParams):
    hash: Optional[str] = None
    action: Optional[str] = None


class NotificationActionSerializer(NotificationApiSerializer):
    hash = serializers.CharField(required=True)
    action = serializers.CharField(required=True)


actions = ["read", "archive"]


class NotificationActionApi(APIView):
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="action", description="one of: " + ", ".join([f"'{a}'" for a in actions]),
                             required=True, type=str, location='path'),
            OpenApiParameter(name="hash", description="hash of notification belonging to current user",
                             required=True, type=str)
        ]
    )
    def post(self, request, **kwargs):
        """
        this expects some low profile update action like e.g.:  'read', 'archive'
        -> ntfy/read hash=XXXX
        """

        serializer = NotificationActionSerializer(
            data={**request.query_params, 'action': kwargs.get('action', None)})  # type: ignore
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        assert isinstance(request.user, User)
        notifications_user = request.user.get_notifications()

        if not notifications_user.exists():
            return Response(_("Notification %(hash)s for user" % params.hash), status=status.HTTP_400_BAD_REQUEST)

        notification = notifications_user.first()
        assert isinstance(notification, Notification)

        if params.action == "read":
            notification.mark_read()
        elif params.action == "archive":
            notification.mark_archived()
