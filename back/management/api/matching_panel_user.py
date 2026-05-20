from django.urls import path
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.api.matching_users_advanced import ManagementPermissionRowSerializer
from management.helpers import IsAdminOrMatchingUser
from management.models.user import User
from management.permissions import MANAGEMENT_PERMISSION_LABELS, ManagementPermission


class MatchingPanelUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    is_matching_user = serializers.BooleanField()
    can_edit_management_permissions = serializers.BooleanField()
    permissions = ManagementPermissionRowSerializer(many=True)


def get_matching_panel_user_data(user: User) -> dict:
    profile = user.profile
    permissions = [
        {
            "permission": permission,
            "codename": permission.codename,
            "label": MANAGEMENT_PERMISSION_LABELS.get(permission),
            "enabled": user.has_perm(permission),
        }
        for permission in ManagementPermission
    ]
    payload = {
        "id": user.id,
        "uuid": str(user.uuid),
        "email": user.email,
        "first_name": profile.first_name,
        "last_name": profile.second_name,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_matching_user": user.has_perm(ManagementPermission.MATCHING_USER),
        "can_edit_management_permissions": user.has_perm(ManagementPermission.APPLY_MANAGEMENT_PERMISSIONS),
        "permissions": ManagementPermissionRowSerializer(permissions, many=True).data,
    }
    return MatchingPanelUserSerializer(payload).data


@extend_schema(
    responses=inline_serializer(
        name="MatchingPanelUserResponse",
        fields={
            "id": serializers.IntegerField(),
            "uuid": serializers.UUIDField(),
            "email": serializers.EmailField(),
            "first_name": serializers.CharField(),
            "last_name": serializers.CharField(),
            "is_staff": serializers.BooleanField(),
            "is_superuser": serializers.BooleanField(),
            "is_matching_user": serializers.BooleanField(),
            "can_edit_management_permissions": serializers.BooleanField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication])
def matching_panel_me(request):
    return Response(get_matching_panel_user_data(request.user))


api_urls = [
    path("api/matching/me/", matching_panel_me, name="matching_panel_me"),
]
