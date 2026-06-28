from django.db.models import Q
from django.urls import path
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from video.models import LivekitSession

from management.api.utils_advanced import FilterSchemaResponseSerializer, filterset_schema_dict
from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.profile import MinimalProfileSerializer
from management.models.user import User
from management.permissions import ManagementPermission


def _format_session_duration(created_at, end_time):
    """Return a human-readable duration, or None when it cannot be calculated."""
    if not created_at or not end_time:
        return None

    total_seconds = int((end_time - created_at).total_seconds())
    if total_seconds < 0:
        return None

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minutes ({seconds}s)"

    return f"{minutes} minutes ({seconds}s)"


class AdvancedLivekitSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LivekitSession
        fields = [
            "uuid",
            "created_at",
            "end_time",
            "is_active",
            "u1",
            "u2",
            "both_have_been_active",
            "random_call_session",
            "u1_was_active",
            "u2_was_active",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        u1 = User.objects.get(id=instance.u1.id)
        u2 = User.objects.get(id=instance.u2.id)

        representation["u1"] = {
            "id": u1.pk,
            "uuid": str(u1.uuid),
            "email": u1.email,
            "profile": MinimalProfileSerializer(u1.profile).data,
        }
        representation["u2"] = {
            "id": u2.pk,
            "uuid": str(u2.uuid),
            "email": u2.email,
            "profile": MinimalProfileSerializer(u2.profile).data,
        }

        if instance.is_active:
            representation["status"] = "active"
        else:
            representation["status"] = "inactive"

        representation["both_have_been_active"] = instance.both_have_been_active
        representation["random_call_session"] = instance.random_call_session
        representation["call_type"] = "random" if instance.random_call_session else "standard"
        representation["u1_was_active"] = instance.u1_was_active
        representation["u2_was_active"] = instance.u2_was_active
        representation["duration"] = _format_session_duration(instance.created_at, instance.end_time)
        return representation


class LivekitSessionFilter(filters.FilterSet):
    u1 = filters.ModelChoiceFilter(field_name="u1", queryset=User.objects.all(), help_text="Filter for u1")

    u2 = filters.ModelChoiceFilter(field_name="u2", queryset=User.objects.all(), help_text="Filter for u2")

    call_type = filters.ChoiceFilter(
        method="filter_by_call_type",
        choices=(("random", "Random call"), ("standard", "Standard")),
        help_text="Filter sessions by call type",
    )

    user_id = filters.NumberFilter(
        method="filter_by_user", help_text="Filter sessions by user id (returns calls where user is u1 or u2)"
    )

    match_participants = filters.CharFilter(
        method="filter_by_match_participants",
        help_text="Comma-separated user ids for both match participants (order-independent)",
    )

    def filter_by_user(self, queryset, name, value):
        if value is not None:
            queryset = queryset.filter(Q(u1_id=value) | Q(u2_id=value))
        return queryset

    def filter_by_match_participants(self, queryset, name, value):
        if not value:
            return queryset
        try:
            user1_id, user2_id = (int(part.strip()) for part in value.split(",", 1))
        except (ValueError, AttributeError):
            return queryset.none()
        return queryset.filter(Q(u1_id=user1_id, u2_id=user2_id) | Q(u1_id=user2_id, u2_id=user1_id))

    def filter_by_call_type(self, queryset, name, value):
        if value == "random":
            return queryset.filter(random_call_session=True)
        if value == "standard":
            return queryset.filter(random_call_session=False)
        return queryset

    created_between = filters.DateFromToRangeFilter(
        field_name="created_at", help_text="Range filter for when the session was created, accepts string datetimes"
    )

    ended_between = filters.DateFromToRangeFilter(
        field_name="end_time", help_text="Range filter for when the session ended, accepts string datetimes"
    )

    active = filters.BooleanFilter(field_name="is_active", help_text="Filter for active sessions")

    both_have_been_active = filters.BooleanFilter(
        field_name="both_have_been_active", help_text="Filter for sessions where both users were active"
    )

    order_by = filters.OrderingFilter(
        fields=(
            ("created_at", "created_at"),
            ("end_time", "end_time"),
            ("u1", "u1"),
            ("u2", "u2"),
            ("is_active", "is_active"),
        ),
        help_text="Order by filter",
    )

    class Meta:
        model = LivekitSession
        fields = ["uuid", "created_at", "end_time", "is_active", "u1", "u2"]


@extend_schema_view(
    list=extend_schema(summary="List Livekit sessions"),
    retrieve=extend_schema(summary="Retrieve Livekit session"),
)
class AdvancedVideoCallsViewset(viewsets.ModelViewSet):
    queryset = LivekitSession.objects.all().order_by("-created_at")

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = LivekitSessionFilter

    serializer_class = AdvancedLivekitSessionSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]

    def get_queryset(self):
        user = self.request.user
        if not isinstance(user, User):
            return LivekitSession.objects.none()
        if user.is_staff:
            return LivekitSession.objects.all()
        elif user.has_perm(ManagementPermission.MATCHING_USER):
            managed_users = user.managed_users_queryset(active_only=False)
            return LivekitSession.objects.filter(Q(u1__in=managed_users) | Q(u2__in=managed_users))

    def check_management_user_access(self, session, request):
        user = session.get_partner(request.user)

        if not request.user.is_staff and not request.user.has_perm(ManagementPermission.MATCHING_USER):
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)

        if not request.user.is_staff and not request.user.has_management_access(user):
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)
        return True, None

    @extend_schema(responses={200: FilterSchemaResponseSerializer})
    @action(detail=False, methods=["get"])
    def get_filter_schema(self, request, include_lookup_expr=False):
        # 1 - retrieve all the filters
        filterset = self.filterset_class()
        _filters = filterset_schema_dict(filterset, include_lookup_expr, "/api/video-calls/livekit-sessions/", request)

        return Response({"filters": _filters, "lists": []})

    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            return super().get_object()
        else:
            return super().get_queryset().get(uuid=self.kwargs["pk"])


api_urls = [
    path("api/matching/video_calls/", AdvancedVideoCallsViewset.as_view({"get": "list"})),
    path("api/matching/video_calls/filters/", AdvancedVideoCallsViewset.as_view({"get": "get_filter_schema"})),
    path("api/matching/video_calls/<str:pk>/", AdvancedVideoCallsViewset.as_view({"get": "retrieve"})),
]
