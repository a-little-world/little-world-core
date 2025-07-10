from django.db.models import Q
from django.urls import path
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS
from management.api.utils_advanced import filterset_schema_dict
from management.controller import unmatch_users
from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.matches import Match
from management.models.profile import MinimalProfileSerializer
from management.models.state import State
from management.models.user import User
from management.api.match_journey_filter_list import determine_match_bucket


class AdvancedMatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = [
            "uuid",
            "created_at",
            "updated_at",
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
            "id": user1.id,
            "hash": user1.hash,
            "email": user1.email,
            "profile": MinimalProfileSerializer(user1.profile).data,
        }
        representation["user2"] = {
            "id": user2.id,
            "hash": user2.hash,
            "email": user2.email,
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
            representation["report_unmatch"] = instance.report_unmatch

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
        selected_filter = next(filter(lambda entry: entry.name == value, MATCH_JOURNEY_FILTERS))
        if selected_filter.queryset:
            return selected_filter.queryset(queryset)
        else:
            return queryset

    class Meta:
        model = Match
        fields = ["uuid", "created_at", "updated_at", "active", "confirmed", "user1", "user2"]


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
        if user.is_staff:
            return Match.objects.all()
        elif user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Match.objects.filter(
                Q(user1__in=user.state.managed_users.all()) | Q(user2__in=user.state.managed_users.all())
            )

    def check_management_user_access(self, match, request):
        user = match.get_partner(request.user)

        if not request.user.is_staff and not request.user.state.has_extra_user_permission(
            State.ExtraUserPermissionChoices.MATCHING_USER
        ):
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)

        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=user.pk).exists():
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)
        return True, None

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
    def resolve_match(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        if obj.user1.is_staff or obj.user2.is_staff:
            return Response({"msg": "One of the users is a staff member and cannot be unmatch"}, status=400)

        if (
            obj.user1.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
            or obj.user2.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
            or obj.user2.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
            or obj.user2.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
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
            return super().get_queryset().get(uuid=self.kwargs["pk"])
        
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
    path("api/matching/matches/filters/", AdvancedMatchViewset.as_view({"get": "get_filter_schema"})),
    path("api/matching/matches/<pk>/", AdvancedMatchViewset.as_view({"get": "retrieve"})),
    path("api/matching/matches/<pk>/resolve/", AdvancedMatchViewset.as_view({"post": "resolve_match"})),
    path("api/matching/matches/<pk>/completed_off_plattform/", AdvancedMatchViewset.as_view({"post": "set_completed_off_plattform"})),
    path("api/matching/matches/<pk>/notes/", AdvancedMatchViewset.as_view({"get": "notes", "post": "notes"})),
]
