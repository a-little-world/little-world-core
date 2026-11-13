from chat.models import Message
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.urls import path
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from management.analytics.match_journey.detail import (
    match_stats_retrieve_extra,
    match_weekly_activity_details,
    match_weekly_activity_retrieve_extra,
)
from management.api.export_utils import build_paginated_export_response, ensure_export_fields
from management.api.match_journey_filter_list import (
    MATCH_JOURNEY_FILTERS,
    determine_match_buckets,
    get_match_bucket_label,
    match_bucket_map,
)
from management.api.utils_advanced import (
    FilterSchemaResponseSerializer,
    apply_journey_bucket_fields,
    enrich_report_unmatch_with_user_info,
    filterset_schema_dict,
    parse_bool_query_param,
)
from management.controller import unmatch_users
from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.match_success import ACTIVE_VERSION_ID, annotate_match_tokens, match_tokens
from management.models.matches import Match
from management.models.profile import MinimalProfileSerializer, Profile
from management.models.unconfirmed_matches import MatchType
from management.models.user import User
from management.permissions import ManagementPermission


def _apply_match_bucket_representation(representation: dict, match_pk: int, context: dict) -> None:
    determine_bucket = context.get("determine_bucket", True)
    all_buckets = context.get("all_buckets", False)
    if not determine_bucket and not all_buckets:
        return

    # Prefer a request-scoped map (list page or retrieve). Fallback is still one classify
    # pass per match via ``determine_match_buckets`` — never the old per-cell ``.exists()`` loop.
    bucket_map = context.get("bucket_map")
    if bucket_map is not None and not all_buckets:
        bucket = bucket_map.get(match_pk)
        category_buckets = [bucket] if bucket else []
    else:
        category_buckets = determine_match_buckets(match_pk, all_lists=False)
    all_bucket_names = determine_match_buckets(match_pk, all_lists=True) if all_buckets else None
    apply_journey_bucket_fields(
        representation,
        category_buckets=category_buckets,
        all_buckets=all_bucket_names,
        determine_bucket=determine_bucket,
        include_all_buckets=all_buckets,
        label_fn=get_match_bucket_label,
    )


MATCH_MESSAGE_EXPORT_FIELDS = frozenset(
    {
        "first_message_from_learner",
        "first_message_from_volunteer",
        "most_recent_message_from_learner",
        "most_recent_message_from_volunteer",
    }
)


def _resolve_match_learner_and_volunteer(match: Match) -> tuple[User | None, User | None]:
    u1, u2 = match.user1, match.user2
    u1_type = u1.profile.user_type
    u2_type = u2.profile.user_type
    if u1_type == Profile.TypeChoices.LEARNER and u2_type == Profile.TypeChoices.VOLUNTEER:
        return u1, u2
    if u2_type == Profile.TypeChoices.LEARNER and u1_type == Profile.TypeChoices.VOLUNTEER:
        return u2, u1
    return None, None


def _message_created_at(sender: User, recipient: User, *, most_recent: bool):
    qs = Message.objects.filter(sender=sender, recipient=recipient)
    if most_recent:
        return qs.aggregate(ts=Max("created"))["ts"]
    return qs.order_by("created").values_list("created", flat=True).first()


def _match_message_export_fields(match: Match) -> dict[str, str | None]:
    dt_field = serializers.DateTimeField()
    empty = dict.fromkeys(MATCH_MESSAGE_EXPORT_FIELDS, None)
    learner, volunteer = _resolve_match_learner_and_volunteer(match)
    if learner is None or volunteer is None:
        return empty

    def _fmt(dt):
        return None if dt is None else dt_field.to_representation(dt)

    return {
        "first_message_from_learner": _fmt(_message_created_at(learner, volunteer, most_recent=False)),
        "first_message_from_volunteer": _fmt(_message_created_at(volunteer, learner, most_recent=False)),
        "most_recent_message_from_learner": _fmt(_message_created_at(learner, volunteer, most_recent=True)),
        "most_recent_message_from_volunteer": _fmt(_message_created_at(volunteer, learner, most_recent=True)),
    }


def _apply_match_message_export_fields(target: dict, match: Match, requested_fields: set[str] | None = None) -> None:
    message_fields = _match_message_export_fields(match)
    if requested_fields is None:
        target.update(message_fields)
        return
    for field_name in MATCH_MESSAGE_EXPORT_FIELDS:
        if field_name in requested_fields:
            target[field_name] = message_fields[field_name]


MATCH_UNMATCH_EXPORT_FIELDS = frozenset(
    {
        "unmatching_type",
        "unmatch_reason",
        "is_manual_unmatch",
    }
)


def _parse_report_unmatch_user_id(user_id_raw) -> int | None:
    if user_id_raw in (None, "no unmatcher specified"):
        return None
    try:
        return int(user_id_raw)
    except (TypeError, ValueError):
        return None


def _is_manual_unmatch(closing_entry: dict, match: Match) -> bool:
    kind = closing_entry.get("kind")
    user_id = _parse_report_unmatch_user_id(closing_entry.get("user_id"))

    if kind == "ghosted":
        return False
    if kind in ("unmatch", "report", "user_deleted"):
        if user_id is None:
            return True
        return user_id not in (match.user1_id, match.user2_id)
    return False


def _match_unmatch_export_fields(match: Match) -> dict[str, str | bool | None]:
    empty = dict.fromkeys(MATCH_UNMATCH_EXPORT_FIELDS, None)
    if match.active:
        return empty

    entries = match.report_unmatch if isinstance(match.report_unmatch, list) else []
    if not entries:
        return empty

    closing_entry = entries[-1]
    return {
        "unmatching_type": closing_entry.get("kind"),
        "unmatch_reason": closing_entry.get("reason"),
        "is_manual_unmatch": _is_manual_unmatch(closing_entry, match),
    }


def _apply_match_unmatch_export_fields(target: dict, match: Match, requested_fields: set[str] | None = None) -> None:
    unmatch_fields = _match_unmatch_export_fields(match)
    if requested_fields is None:
        target.update(unmatch_fields)
        return
    for field_name in MATCH_UNMATCH_EXPORT_FIELDS:
        if field_name in requested_fields:
            target[field_name] = unmatch_fields[field_name]


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

        _apply_match_bucket_representation(representation, instance.pk, getattr(self, "context", {}))
        representation["match_tokens"] = match_tokens(instance)
        representation["match_token_version"] = ACTIVE_VERSION_ID

        return representation


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

    @staticmethod
    def _set_nested_value(target: dict, path: list[str], value):
        cursor = target
        for part in path[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[path[-1]] = value

    @staticmethod
    def _get_nested_value(source: dict, path: list[str]):
        value = source
        for part in path:
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    def _serialize_export_user(self, user: User):
        return {
            "id": user.id,
            "uuid": str(user.uuid),
            "email": user.email,
            "has_match_priority": user.state.has_match_priority,
            "profile": {
                "first_name": user.profile.first_name,
                "second_name": user.profile.second_name,
                "user_type": user.profile.user_type,
            },
        }

    def to_representation(self, instance):
        requested_fields = self.context.get("selected_fields")
        representation = super().to_representation(instance)

        if not requested_fields:
            representation["user1"] = self._serialize_export_user(instance.user1)
            representation["user2"] = self._serialize_export_user(instance.user2)

            if instance.confirmed:
                representation["status"] = "confirmed"
            elif instance.support_matching:
                representation["status"] = "support"
            else:
                representation["status"] = "unconfirmed"

            if not instance.active:
                representation["status"] = "reported_or_removed"

            _apply_match_bucket_representation(representation, instance.pk, self.context)
            _apply_match_message_export_fields(representation, instance)
            _apply_match_unmatch_export_fields(representation, instance)
            representation["match_tokens"] = match_tokens(instance)
            representation["match_token_version"] = ACTIVE_VERSION_ID
            return representation

        requested_set = set(requested_fields)
        filtered = {}

        for field_name in requested_set:
            if "." in field_name:
                continue
            if field_name in representation:
                filtered[field_name] = representation[field_name]

        if "status" in requested_set:
            if instance.confirmed:
                filtered["status"] = "confirmed"
            elif instance.support_matching:
                filtered["status"] = "support"
            else:
                filtered["status"] = "unconfirmed"
            if not instance.active:
                filtered["status"] = "reported_or_removed"

        if (
            "bucket" in requested_set
            or "bucket_label" in requested_set
            or "buckets" in requested_set
            or "bucket_labels" in requested_set
        ):
            _apply_match_bucket_representation(filtered, instance.pk, self.context)
            if "bucket" not in requested_set:
                filtered.pop("bucket", None)
            if "bucket_label" not in requested_set:
                filtered.pop("bucket_label", None)
            if "buckets" not in requested_set:
                filtered.pop("buckets", None)
            if "bucket_labels" not in requested_set:
                filtered.pop("bucket_labels", None)

        _apply_match_message_export_fields(filtered, instance, requested_set)
        _apply_match_unmatch_export_fields(filtered, instance, requested_set)

        if "match_tokens" in requested_set:
            filtered["match_tokens"] = match_tokens(instance)
            filtered["match_token_version"] = ACTIVE_VERSION_ID

        for user_prefix, user in (("user1", instance.user1), ("user2", instance.user2)):
            full_user = self._serialize_export_user(user)
            user_requested = [
                field for field in requested_set if field == user_prefix or field.startswith(f"{user_prefix}.")
            ]
            if not user_requested:
                continue

            if user_prefix in requested_set:
                filtered[user_prefix] = full_user
                continue

            for field_name in user_requested:
                path = field_name.split(".")
                nested_value = self._get_nested_value(full_user, path[1:])
                self._set_nested_value(filtered, path, nested_value)

        return ensure_export_fields(filtered, requested_fields)


MATCH_EXPORT_COLUMN_NAMES = (
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
    "status",
    "bucket",
    "bucket_label",
    "first_message_from_learner",
    "first_message_from_volunteer",
    "most_recent_message_from_learner",
    "most_recent_message_from_volunteer",
    "unmatching_type",
    "unmatch_reason",
    "is_manual_unmatch",
    "match_tokens",
    "user1.id",
    "user1.uuid",
    "user1.email",
    "user1.has_match_priority",
    "user1.profile.first_name",
    "user1.profile.second_name",
    "user1.profile.user_type",
    "user2.id",
    "user2.uuid",
    "user2.email",
    "user2.has_match_priority",
    "user2.profile.first_name",
    "user2.profile.second_name",
    "user2.profile.user_type",
)


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
    retrieve=extend_schema(summary="Retrieve match", responses={200: AdvancedMatchSerializer}),
)
class AdvancedMatchViewset(viewsets.ModelViewSet):
    queryset = Match.objects.all().order_by("-created_at")

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = MatchFilter

    serializer_class = AdvancedMatchSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]

    def get_serializer_context(self):
        all_buckets = parse_bool_query_param(self.request.query_params.get("all_buckets"))
        determine_bucket_param = self.request.query_params.get("determine_bucket")
        determine_bucket = (
            parse_bool_query_param(determine_bucket_param) if determine_bucket_param is not None else True
        )
        context = {"determine_bucket": determine_bucket, "all_buckets": all_buckets}
        bucket_map = getattr(self, "_bucket_map", None)
        if bucket_map is not None:
            context["bucket_map"] = bucket_map
        return context

    def paginate_queryset(self, queryset):
        """Classify the page's buckets in one pass, once the page rows are known.

        Here rather than in ``get_queryset`` because only the paginated slice needs
        classifying — the full queryset is thousands of matches. DRF calls this before
        building the serializer, so ``get_serializer_context`` picks the map up.
        """
        page = super().paginate_queryset(queryset)
        if page is not None and self.get_serializer_context().get("determine_bucket"):
            self._bucket_map = match_bucket_map([m.pk for m in page], matches=page)
        return page

    def get_queryset(self):
        user = self.request.user
        # Annotated here so the serializer's per-row token lookup is free: without it a
        # 25-row page cost 75 queries (one session aggregate plus two FK fetches each).
        base = (
            annotate_match_tokens(Match.objects.all()).exclude(match_type=MatchType.TEMPORARY).order_by("-created_at")
        )
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

    @extend_schema(responses={200: FilterSchemaResponseSerializer})
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
        # Retrieve skips paginate_queryset, so build the map here — same classify pass as list.
        # Pass the annotated instance so classify reuses its call-time SUM (no second annotate).
        if self.get_serializer_context().get("determine_bucket"):
            self._bucket_map = match_bucket_map([instance.pk], matches=[instance])
        serializer = self.get_serializer(instance)
        data = dict(serializer.data)
        data.update(match_stats_retrieve_extra(instance))
        data.update(match_weekly_activity_retrieve_extra(instance))
        return Response(data)

    @extend_schema(summary="Retrieve weekly activity details for a match")
    @action(detail=True, methods=["get"])
    def weekly_activity_details(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        week_raw = request.query_params.get("week")
        if week_raw is None:
            return Response({"msg": "week query parameter is required"}, status=400)
        try:
            week = int(week_raw)
        except (TypeError, ValueError):
            return Response({"msg": "week must be an integer"}, status=400)
        if week < 1:
            return Response({"msg": "week must be >= 1"}, status=400)

        return Response(match_weekly_activity_details(obj, week))

    @action(detail=True, methods=["post"])
    def set_completed_off_plattform(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()
        obj.completed_off_plattform = request.data["completed_off_plattform"]
        obj.save()
        return Response({"msg": "Match completed off plattform set"})

    @extend_schema(
        responses={
            200: inline_serializer(name="MatchNotesResponse", fields={"notes": serializers.CharField()}),
        }
    )
    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        if request.method == "POST":
            obj.notes = request.data["notes"]
            obj.save()
            return Response({"notes": obj.notes or ""})
        else:
            if not obj.notes:
                obj.notes = ""
                obj.save()
            return Response({"notes": obj.notes or ""})


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def matches_export(request):
    selected_fields_raw = request.query_params.get("fields", "")
    selected_fields = {field.strip() for field in selected_fields_raw.split(",") if field.strip()}

    user = request.user
    queryset = Match.objects.all().exclude(match_type=MatchType.TEMPORARY).order_by("-created_at")
    if not user.is_staff:
        if isinstance(user, User) and user.has_perm(ManagementPermission.MATCHING_USER):
            managed_users = user.managed_users_queryset(active_only=False)
            queryset = queryset.filter(Q(user1__in=managed_users) | Q(user2__in=managed_users))

    needs_user1 = any(field == "user1" or field.startswith("user1.") for field in selected_fields)
    needs_user2 = any(field == "user2" or field.startswith("user2.") for field in selected_fields)
    if not selected_fields or needs_user1 or needs_user2:
        select_related_fields = []
        if not selected_fields or needs_user1:
            select_related_fields.extend(["user1", "user1__profile", "user1__state"])
        if not selected_fields or needs_user2:
            select_related_fields.extend(["user2", "user2__profile", "user2__state"])
        queryset = queryset.select_related(*select_related_fields)

    queryset = MatchFilter(request.query_params, queryset=queryset).qs
    all_buckets = parse_bool_query_param(request.query_params.get("all_buckets"))
    determine_bucket_param = request.query_params.get("determine_bucket")
    determine_bucket = parse_bool_query_param(determine_bucket_param) if determine_bucket_param is not None else True
    return build_paginated_export_response(
        request,
        queryset,
        ExportMatchSerializer,
        allowed_fields=MATCH_EXPORT_COLUMN_NAMES,
        extra_serializer_context={"determine_bucket": determine_bucket, "all_buckets": all_buckets},
    )


api_urls = [
    path("api/matching/matches/", AdvancedMatchViewset.as_view({"get": "list"})),
    path("api/matching/matches_export/", matches_export),
    path("api/matching/matches/filters/", AdvancedMatchViewset.as_view({"get": "get_filter_schema"})),
    path("api/matching/matches/<pk>/", AdvancedMatchViewset.as_view({"get": "retrieve"})),
    path(
        "api/matching/matches/<pk>/weekly_activity_details/",
        AdvancedMatchViewset.as_view({"get": "weekly_activity_details"}),
    ),
    path("api/matching/matches/<pk>/resolve/", AdvancedMatchViewset.as_view({"post": "resolve_match"})),
    path(
        "api/matching/matches/<pk>/completed_off_plattform/",
        AdvancedMatchViewset.as_view({"post": "set_completed_off_plattform"}),
    ),
    path("api/matching/matches/<pk>/notes/", AdvancedMatchViewset.as_view({"get": "notes", "post": "notes"})),
]
