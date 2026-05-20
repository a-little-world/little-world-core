from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.urls import path
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, viewsets

from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.profile import MinimalProfileSerializer
from management.models.user import User
from management.permissions import MANAGEMENT_PERMISSION_LABELS, ManagementPermission


class MatchingUserFilter(filters.FilterSet):
    order_by = filters.OrderingFilter(
        fields=(
            ("date_joined", "date_joined"),
            ("last_login", "last_login"),
            ("email", "email"),
        ),
        help_text="Order by field",
    )

    search = filters.CharFilter(method="filter_search", label="Search")

    def filter_search(self, queryset, name, value):
        return queryset.annotate(
            full_name=Concat("profile__first_name", Value(" "), "profile__second_name", output_field=CharField())
        ).filter(
            Q(email__icontains=value)
            | Q(profile__first_name__icontains=value)
            | Q(profile__second_name__icontains=value)
            | Q(full_name__icontains=value)
        )

    class Meta:
        model = User
        fields = ["search"]


class ManagementPermissionRowSerializer(serializers.Serializer):
    permission = serializers.CharField()
    codename = serializers.CharField()
    label = serializers.CharField(required=False, allow_null=True)
    enabled = serializers.BooleanField()


class ManagementPermissionRowsSerializer(serializers.Serializer):
    """Serializes all management permissions for a user instance."""

    def to_representation(self, user: User):
        rows = [
            {
                "permission": permission,
                "codename": permission.codename,
                "label": MANAGEMENT_PERMISSION_LABELS.get(permission),
                "enabled": user.has_perm(permission),
            }
            for permission in ManagementPermission
        ]
        return ManagementPermissionRowSerializer(rows, many=True).data


class MatchingUserSerializer(serializers.ModelSerializer):
    profile = MinimalProfileSerializer(read_only=True)
    permissions = ManagementPermissionRowsSerializer(source="*", read_only=True)

    class Meta:
        model = User
        fields = [
            "uuid",
            "id",
            "email",
            "date_joined",
            "last_login",
            "is_staff",
            "is_superuser",
            "profile",
            "permissions",
        ]


@extend_schema_view(
    list=extend_schema(summary="List users with matching_user permission and their management permissions"),
)
class MatchingUsersViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MatchingUserSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = MatchingUserFilter
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]

    def get_queryset(self):
        return (
            User.objects.filter(
                user_permissions__codename=ManagementPermission.MATCHING_USER.codename,
                user_permissions__content_type__app_label="management",
                user_permissions__content_type__model="state",
            )
            .distinct()
            .order_by("-date_joined")
        )

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data["can_edit_management_permissions"] = request.user.has_perm(
            ManagementPermission.APPLY_MANAGEMENT_PERMISSIONS
        )
        return response


api_urls = [
    path("api/matching/matching_users/", MatchingUsersViewSet.as_view({"get": "list"})),
]
