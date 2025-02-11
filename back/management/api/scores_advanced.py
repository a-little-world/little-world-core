from django.db.models import Q
from django.urls import path
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS
from management.api.scores import instantly_possible_matches
from management.api.user_advanced import AdvancedUserSerializer
from management.api.utils_advanced import filterset_schema_dict
from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.scores import TwoUserMatchingScore
from management.models.state import State
from management.models.user import User


class TwoUserMatchingScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = TwoUserMatchingScore
        fields = ["id", "user1", "user2", "score", "matchable", "scoring_results", "latest_update"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user1 = User.objects.get(id=instance.user1.id)
        user2 = User.objects.get(id=instance.user2.id)

        representation["user1"] = AdvancedUserSerializer(user1).data
        representation["user2"] = AdvancedUserSerializer(user2).data

        return representation


class TwoUserMatchingScoreFilter(filters.FilterSet):
    user1 = filters.ModelChoiceFilter(field_name="user1", queryset=User.objects.all(), help_text="Filter for user1")

    user2 = filters.ModelChoiceFilter(field_name="user2", queryset=User.objects.all(), help_text="Filter for user2")

    score_gte = filters.NumberFilter(
        field_name="score", lookup_expr="gte", help_text="Filter for scores greater than or equal to"
    )

    score_lte = filters.NumberFilter(
        field_name="score", lookup_expr="lte", help_text="Filter for scores less than or equal to"
    )

    matchable = filters.BooleanFilter(field_name="matchable", help_text="Filter for matchable scores")

    latest_update_between = filters.DateFromToRangeFilter(
        field_name="latest_update",
        help_text="Range filter for when the score was last updated, accepts string datetimes",
    )

    class Meta:
        model = TwoUserMatchingScore
        fields = ["user1", "user2", "score", "matchable", "latest_update"]

    current_match_suggestion = filters.BooleanFilter(
        method="filter_current_match_suggestion", help_text="Filter for current match suggestions"
    )

    def filter_current_match_suggestion(self, queryset, name, value):
        if value:
            suggested_matches = instantly_possible_matches()
            user_pairs = [(user1, user2) for user1, user2 in suggested_matches]
            queries = [
                Q(user1_id=user1, user2_id=user2) | Q(user1_id=user2, user2_id=user1) for user1, user2 in user_pairs
            ]
            if len(queries) == 0:
                return queryset.none()
            query = queries.pop()
            for item in queries:
                query |= item
            return queryset.filter(query)
        return queryset


@extend_schema_view(
    list=extend_schema(summary="List matching scores"),
    retrieve=extend_schema(summary="Retrieve matching score"),
)
class TwoUserMatchingScoreViewset(viewsets.ModelViewSet):
    queryset = TwoUserMatchingScore.objects.all().order_by("-latest_update")

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = TwoUserMatchingScoreFilter

    serializer_class = TwoUserMatchingScoreSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return TwoUserMatchingScore.objects.all()
        elif user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return TwoUserMatchingScore.objects.filter(
                Q(user1__in=user.state.managed_users.all()) | Q(user2__in=user.state.managed_users.all())
            )

    @action(detail=False, methods=["get"])
    def get_filter_schema(self, request, include_lookup_expr=False):
        # 1 - retrieve all the filters
        filterset = self.filterset_class()
        _filters = filterset_schema_dict(filterset, include_lookup_expr, "/api/matching/scores/", request)

        return Response({"filters": _filters, "lists": [entry.to_dict() for entry in MATCH_JOURNEY_FILTERS]})

    def get_object(self):
        return super().get_object()


api_urls = [
    path("api/matching/scores/", TwoUserMatchingScoreViewset.as_view({"get": "list"})),
    path("api/matching/scores/filters/", TwoUserMatchingScoreViewset.as_view({"get": "get_filter_schema"})),
    path("api/matching/scores/<pk>/", TwoUserMatchingScoreViewset.as_view({"get": "retrieve"})),
]
