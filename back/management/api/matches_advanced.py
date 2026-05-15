from chat.models import Message
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.urls import path
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from video.models import LivekitSession

from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS, determine_match_bucket
from management.api.utils_advanced import enrich_report_unmatch_with_user_info, filterset_schema_dict
from management.controller import unmatch_users
from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.matches import Match
from management.models.profile import MinimalProfileSerializer
from management.models.unconfirmed_matches import MatchType
from management.models.user import User
from management.permissions import ManagementPermission


class AdvancedMatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = [
            "uuid",
            "created_at",
            "updated_at",
            "match_type",
            "active",
            "confirmed",
            "latest_interaction_at",
            "notes",
            "total_messages_counter",
            "total_mutal_video_calls_counter",
            "user1",
            "user2",
            "completed_off_plattform",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user1 = User.objects.get(id=instance.user1.id)
        user2 = User.objects.get(id=instance.user2.id)

        representation["user1"] = {
            "id": user1.pk,
            "uuid": str(user1.uuid),
            "email": user1.email,
            "has_match_priority": user1.state.has_match_priority,
            "profile": MinimalProfileSerializer(user1.profile).data,
        }
        representation["user2"] = {
            "id": user2.pk,
            "uuid": str(user2.uuid),
            "email": user2.email,
            "has_match_priority": user2.state.has_match_priority,
            "profile": MinimalProfileSerializer(user2.profile).data,
        }

        # DO this seralization only if it's not a ProposedMatch
        if hasattr(instance, "confirmed"):
            if instance.confirmed:
                representation["status"] = "confirmed"
            elif instance.support_matching:
                representation["status"] = "support"
            else:
                representation["status"] = "unconfirmed"

        if hasattr(instance, "report_unmatch"):
            representation["report_unmatch"] = enrich_report_unmatch_with_user_info(instance.report_unmatch, instance)

        if hasattr(instance, "active"):
            if not instance.active:
                representation["status"] = "reported_or_removed"
        else:
            representation["status"] = "proposed"

        bucket = determine_match_bucket(instance.pk)
        if bucket is not None:
            representation["bucket"] = bucket
        else:
            representation["bucket"] = "unknown"

        return representation


def _match_stats_retrieve_extra(match: Match) -> dict:
    """
    Read-only match stats for single-match GET (retrieve) only.
    Not stored on Match; omitted from list/export serializers.
    """
    u1 = match.user1
    u2 = match.user2
    dt_field = serializers.DateTimeField()

    def _format_datetime_for_json(dt):
        """Serialize a datetime for the JSON body (DRF/ISO-8601); None if there is no timestamp."""
        return None if dt is None else dt_field.to_representation(dt)

    # Same directed pair logic as sync_match_counters — do not use Chat.get_chat() alone:
    # it returns only the newest chat row, which can be an empty temporary chat while real messages sit on an older chat.
    last_msg_u1_at = Message.objects.filter(sender=u1, recipient=u2).aggregate(ts=Max("created"))["ts"]
    last_msg_u2_at = Message.objects.filter(sender=u2, recipient=u1).aggregate(ts=Max("created"))["ts"]

    pair_q = Q(u1=u1, u2=u2) | Q(u1=u2, u2=u1)
    last_video_at = (
        LivekitSession.objects.filter(pair_q, both_have_been_active=True)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )

    return {
        "last_video_call_at": _format_datetime_for_json(last_video_at),
        "user1_last_message_at": _format_datetime_for_json(last_msg_u1_at),
        "user2_last_message_at": _format_datetime_for_json(last_msg_u2_at),
    }


class ExportMatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = [
            "uuid",
            "created_at",
            "updated_at",
            "match_type",
            "active",
            "confirmed",
            "latest_interaction_at",
            "notes",
            "total_messages_counter",
            "total_mutal_video_calls_counter",
            "completed_off_plattform",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        representation["user1"] = {
            "id": instance.user1.id,
            "uuid": str(instance.user1.uuid),
            "email": instance.user1.email,
            "has_match_priority": instance.user1.state.has_match_priority,
            "profile": {
                "first_name": instance.user1.profile.first_name,
                "second_name": instance.user1.profile.second_name,
                "user_type": instance.user1.profile.user_type,
            },
        }
        representation["user2"] = {
            "id": instance.user2.id,
            "uuid": str(instance.user2.uuid),
            "email": instance.user2.email,
            "has_match_priority": instance.user2.state.has_match_priority,
            "profile": {
                "first_name": instance.user2.profile.first_name,
                "second_name": instance.user2.profile.second_name,
                "user_type": instance.user2.profile.user_type,
            },
        }

        if instance.confirmed:
            representation["status"] = "confirmed"
        elif instance.support_matching:
            representation["status"] = "support"
        else:
            representation["status"] = "unconfirmed"

        if not instance.active:
            representation["status"] = "reported_or_removed"

        bucket = determine_match_bucket(instance.pk)
        if bucket is not None:
            representation["bucket"] = bucket
        else:
            representation["bucket"] = "unknown"

        return representation


class MatchFilter(filters.FilterSet):
    user1 = filters.ModelChoiceFilter(field_name="user1", queryset=User.objects.all(), help_text="Filter for user1")

    user2 = filters.ModelChoiceFilter(field_name="user2", queryset=User.objects.all(), help_text="Filter for user2")

    created_between = filters.DateFromToRangeFilter(
        field_name="created_at", help_text="Range filter for when the match was created, accepts string datetimes"
    )

    updated_between = filters.DateFromToRangeFilter(
        field_name="updated_at", help_text="Range filter for when the match was last updated, accepts string datetimes"
    )

    active = filters.BooleanFilter(field_name="active", help_text="Filter for active matches")

    confirmed = filters.BooleanFilter(field_name="confirmed", help_text="Filter for confirmed matches")
    completed_off_plattform = filters.BooleanFilter(
        field_name="completed_off_plattform",
        help_text="Filter for matches completed off platform",
    )

    match_type = filters.ChoiceFilter(
        field_name="match_type",
        choices=[
            (MatchType.STANDARD, "Standard"),
            (MatchType.RANDOM_CALL, "Random Call"),
        ],
        help_text="Filter by match type (standard or random_call)",
    )

    order_by = filters.OrderingFilter(
        fields=(
            ("created_at", "created_at"),
            ("updated_at", "updated_at"),
        ),
        help_text="Ordering filter for matches",
    )

    list = filters.ChoiceFilter(
        field_name="list",
        choices=[(entry.name, entry.description) for entry in MATCH_JOURNEY_FILTERS],
        method="filter_list",
        help_text="Filter for users that are part of a list",
    )

    def filter_list(self, queryset, name, value):
        selected_filter = next(filter(lambda entry: entry.name == value, MATCH_JOURNEY_FILTERS), None)
        if selected_filter and selected_filter.queryset:
            return selected_filter.queryset(queryset)
        return queryset

    class Meta:
        model = Match
        fields = [
            "uuid",
            "created_at",
            "updated_at",
            "active",
            "confirmed",
            "completed_off_plattform",
            "match_type",
            "user1",
            "user2",
        ]


@extend_schema_view(
    list=extend_schema(summary="List matches"),
    retrieve=extend_schema(summary="Retrieve match"),
)
class AdvancedMatchViewset(viewsets.ModelViewSet):
    queryset = Match.objects.all().order_by("-created_at")

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = MatchFilter

    serializer_class = AdvancedMatchSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]

    def get_queryset(self):
        user = self.request.user
        base = Match.objects.all().exclude(match_type=MatchType.TEMPORARY).order_by("-created_at")
        if user.is_staff:
            return base
        if isinstance(user, User) and user.has_perm(ManagementPermission.MATCHING_USER):
            managed_users = user.managed_users_queryset(active_only=False)
            return base.filter(Q(user1__in=managed_users) | Q(user2__in=managed_users))
        return base

    def check_management_user_access(self, match: Match, request: Request) -> tuple[bool, Response]:
        current_user = request.user
        if not isinstance(current_user, User):
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)

        user = match.get_partner(current_user)

        if not current_user.is_staff and not current_user.has_perm(ManagementPermission.MATCHING_USER):
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)

        if not current_user.is_staff and not current_user.has_management_access(user):
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)
        return True, Response(status=200)

    @action(detail=False, methods=["get"])
    def get_filter_schema(self, request, include_lookup_expr=False):
        # 1 - retrieve all the filters
        filterset = self.filterset_class()
        _filters = filterset_schema_dict(filterset, include_lookup_expr, "/api/matching/matches/", request)

        return Response({"filters": _filters, "lists": [entry.to_dict() for entry in MATCH_JOURNEY_FILTERS]})

    @extend_schema(
        summary="Resolve a match",
        request=inline_serializer(
            name="ResolveMatchRequest",
            fields={
                "reason": serializers.CharField(help_text="Reason for unmatching the users"),
            },
        ),
    )
    @action(detail=True, methods=["post"])
    def resolve_match(self, request: Request, pk: str | None = None) -> Response:
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, access_response = self.check_management_user_access(obj, request)
        if not has_access:
            return access_response

        if obj.user1.is_staff or obj.user2.is_staff:
            return Response({"msg": "One of the users is a staff member and cannot be unmatch"}, status=400)

        if obj.user1.has_perm(ManagementPermission.MATCHING_USER) or obj.user2.has_perm(
            ManagementPermission.MATCHING_USER
        ):
            return Response({"msg": "One of the users is a matching user and cannot be unmatch"}, status=400)

        reason = request.data.get("reason")
        if not reason:
            return Response({"msg": "Reason is required for unmatching users"}, status=400)

        unmatch_users({obj.user1, obj.user2}, unmatcher=request.user, reason=reason)

        return Response({"msg": "Match resolved"})

    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            return super().get_object()
        else:
            # Use 404-safe lookup so unknown UUIDs do not raise an uncaught DoesNotExist.
            obj = get_object_or_404(super().get_queryset(), uuid=self.kwargs["pk"])
            self.check_object_permissions(self.request, obj)
            return obj

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = dict(serializer.data)
        data.update(_match_stats_retrieve_extra(instance))
        return Response(data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = ExportMatchSerializer(queryset, many=True)

        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def set_completed_off_plattform(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()
        obj.completed_off_plattform = request.data["completed_off_plattform"]
        obj.save()
        return Response({"msg": "Match completed off plattform set"})

    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        if request.method == "POST":
            obj.notes = request.data["notes"]
            obj.save()
            return Response(obj.notes)
        else:
            if not obj.notes:
                obj.notes = ""
                obj.save()
            return Response(obj.notes)


api_urls = [
    path("api/matching/matches/", AdvancedMatchViewset.as_view({"get": "list"})),
    path("api/matching/matches_export/", AdvancedMatchViewset.as_view({"get": "export"})),
    path("api/matching/matches/filters/", AdvancedMatchViewset.as_view({"get": "get_filter_schema"})),
    path("api/matching/matches/<pk>/", AdvancedMatchViewset.as_view({"get": "retrieve"})),
    path("api/matching/matches/<pk>/resolve/", AdvancedMatchViewset.as_view({"post": "resolve_match"})),
    path(
        "api/matching/matches/<pk>/completed_off_plattform/",
        AdvancedMatchViewset.as_view({"post": "set_completed_off_plattform"}),
    ),
    path("api/matching/matches/<pk>/notes/", AdvancedMatchViewset.as_view({"get": "notes", "post": "notes"})),
]
