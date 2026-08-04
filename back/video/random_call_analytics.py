from datetime import datetime, time

from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import DetailedPagination
from management.models.profile import Profile
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from video.analytics.lobbies import (
    annotate_lobby_metrics,
    apply_lobby_ordering,
    filtered_lobby_queryset,
)
from video.analytics.session_detail import build_lobby_session_detail, resolve_lobby_session
from video.analytics.snapshots import build_snapshots, lobby_session_snapshot_to_dict
from video.models import RandomCallLobby


def _parse_analytics_datetime_bound(value: str | None, *, end_of_day: bool = False):
    if not value:
        return None
    parsed_dt = parse_datetime(value)
    if parsed_dt is not None:
        if timezone.is_naive(parsed_dt):
            return timezone.make_aware(parsed_dt)
        return parsed_dt
    parsed_date = parse_date(value)
    if parsed_date is None:
        return None
    bound_time = time.max if end_of_day else time.min
    return timezone.make_aware(datetime.combine(parsed_date, bound_time))


class LobbySessionSnapshotSerializer(serializers.Serializer):
    lobby_uuid = serializers.CharField()
    lobby_name = serializers.CharField()
    start_time = serializers.DateTimeField(allow_null=True)
    end_time = serializers.DateTimeField(allow_null=True)
    day = serializers.CharField(allow_null=True)
    date = serializers.DateField(allow_null=True)
    total_users = serializers.IntegerField()
    first_time_users = serializers.IntegerField()
    returning_users = serializers.IntegerField()
    proposals_total = serializers.IntegerField()
    proposals_accepted = serializers.IntegerField()
    proposals_rejected = serializers.IntegerField()
    proposals_expired = serializers.IntegerField()
    completed_calls = serializers.IntegerField()
    learner_count = serializers.IntegerField()
    volunteer_count = serializers.IntegerField()


class RandomCallLobbySessionSerializer(serializers.Serializer):
    name = serializers.CharField()
    uuid = serializers.CharField()
    is_active = serializers.BooleanField()
    start_time = serializers.DateTimeField(allow_null=True)
    end_time = serializers.DateTimeField(allow_null=True)
    active_users_count = serializers.IntegerField()
    total_users_count = serializers.IntegerField()


class RandomCallSessionUserSerializer(serializers.Serializer):
    uuid = serializers.CharField()
    user_uuid = serializers.CharField()
    user_name = serializers.CharField()
    user_type = serializers.ChoiceField(choices=Profile.TypeChoices.choices, required=True)
    is_active = serializers.BooleanField()
    last_status_checked_at = serializers.DateTimeField(allow_null=True)
    has_pending_match = serializers.BooleanField()


class RandomCallSessionMatchSerializer(serializers.Serializer):
    uuid = serializers.CharField()
    u1_uuid = serializers.CharField()
    u1_name = serializers.CharField()
    u1_user_type = serializers.ChoiceField(choices=Profile.TypeChoices.choices, required=True)
    u2_uuid = serializers.CharField()
    u2_name = serializers.CharField()
    u2_user_type = serializers.ChoiceField(choices=Profile.TypeChoices.choices, required=True)
    u1_accepted = serializers.BooleanField()
    u2_accepted = serializers.BooleanField()
    u1_status = serializers.CharField()
    u2_status = serializers.CharField()
    accepted = serializers.BooleanField()
    rejected = serializers.BooleanField()
    expired = serializers.BooleanField()
    completed = serializers.BooleanField()
    in_session = serializers.BooleanField()
    created_at = serializers.DateTimeField(allow_null=True, required=False)


class RandomCallLobbyParticipantProfileSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    image_type = serializers.CharField()
    avatar_config = serializers.JSONField()
    image = serializers.CharField(allow_null=True, required=False)


class RandomCallLobbyParticipantSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    user_uuid = serializers.CharField()
    user_name = serializers.CharField()
    user_type = serializers.ChoiceField(choices=Profile.TypeChoices.choices, required=True)
    is_active = serializers.BooleanField()
    completed_calls = serializers.IntegerField()
    unsuccessful_proposals = serializers.IntegerField()
    accepted_proposals = serializers.IntegerField()
    longest_call_duration_seconds = serializers.IntegerField()
    profile = RandomCallLobbyParticipantProfileSerializer()


class LobbySessionProposalStatisticsSerializer(serializers.Serializer):
    total_matches = serializers.IntegerField()
    pending_count = serializers.IntegerField()
    accepted_count = serializers.IntegerField()
    rejected_count = serializers.IntegerField()
    expired_count = serializers.IntegerField()
    dangling_count = serializers.IntegerField()


def _serialize_lobby_session_detail(detail: dict) -> dict:
    snapshot_data = detail["snapshot"]
    return {
        "snapshot": LobbySessionSnapshotSerializer(snapshot_data).data if snapshot_data else None,
        "lobby": RandomCallLobbySessionSerializer(detail["lobby"]).data,
        "active_users": RandomCallSessionUserSerializer(detail["active_users"], many=True).data,
        "lobby_participants": RandomCallLobbyParticipantSerializer(detail["lobby_participants"], many=True).data,
        "match_proposals": {
            key: RandomCallSessionMatchSerializer(matches, many=True).data
            for key, matches in detail["match_proposals"].items()
        },
        "proposal_statistics": LobbySessionProposalStatisticsSerializer(detail["proposal_statistics"]).data,
    }


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def list_lobby_stats(request):
    """Paginated lobby session snapshots."""
    lobby_name = request.query_params.get("lobby_name", "default")
    from_dt = _parse_analytics_datetime_bound(request.query_params.get("from"))
    to_dt = _parse_analytics_datetime_bound(request.query_params.get("to"), end_of_day=True)
    ordering = request.query_params.get("ordering")

    qs = filtered_lobby_queryset(lobby_name=lobby_name, from_dt=from_dt, to_dt=to_dt)
    qs = annotate_lobby_metrics(qs)
    try:
        qs = apply_lobby_ordering(qs, ordering)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)

    paginator = DetailedPagination()
    page = paginator.paginate_queryset(qs, request)
    if page is None:
        return Response({"results": []})

    snapshots = build_snapshots(page)
    results = [lobby_session_snapshot_to_dict(snapshots[lobby.uuid]) for lobby in page if lobby.uuid in snapshots]
    return paginator.get_paginated_response(results)


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def get_lobby_session(request, lobby_name="default"):
    """
    Lobby session detail: analytics snapshot plus live proposal/participant breakdown.

    Query params:
    - lobby_uuid (optional): specific lobby session instance. If omitted, resolves the
      active lobby for lobby_name, or the most recent finished one.
    """
    lobby_uuid_param = request.query_params.get("lobby_uuid", None)
    try:
        lobby = resolve_lobby_session(lobby_name, lobby_uuid=lobby_uuid_param)
    except RandomCallLobby.DoesNotExist:
        return Response({"error": "Lobby not found"}, status=404)
    if lobby is None:
        return Response({"error": "Lobby not found"}, status=404)

    detail = build_lobby_session_detail(lobby)
    return Response(_serialize_lobby_session_detail(detail), status=200)


api_urls = [
    path(
        "api/random_calls/analytics/lobbies",
        list_lobby_stats,
    ),
    path(
        "api/random_calls/analytics/lobby/<str:lobby_name>/session",
        get_lobby_session,
    ),
]
