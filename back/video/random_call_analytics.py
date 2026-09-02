from django.urls import path
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import DetailedPagination
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from video.analytics.display_time import parse_analytics_datetime_bound
from video.analytics.instance_detail import build_lobby_instance_detail
from video.analytics.lobbies import (
    annotate_lobby_metrics,
    apply_lobby_ordering,
    filtered_lobby_queryset,
)
from video.analytics.snapshots import build_snapshots, lobby_instance_snapshot_to_dict
from video.lobby_resolution import InvalidLobbyUuid, resolve_lobby_instance


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def list_lobby_stats(request):
    """Paginated lobby instance snapshots."""
    lobby_name = request.query_params.get("lobby_name", "default")
    from_dt = parse_analytics_datetime_bound(request.query_params.get("from"))
    to_dt = parse_analytics_datetime_bound(request.query_params.get("to"), end_of_day=True)
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
        return Response({"count": 0, "next": None, "previous": None, "results": []})

    snapshots = build_snapshots(page)
    results = [lobby_instance_snapshot_to_dict(snapshots[lobby.uuid]) for lobby in page if lobby.uuid in snapshots]
    return paginator.get_paginated_response(results)


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def list_lobby_trends(request):
    """Chronological lobby instance snapshots for trend charts (no pagination)."""
    lobby_name = request.query_params.get("lobby_name", "default")
    from_dt = parse_analytics_datetime_bound(request.query_params.get("from"))
    to_dt = parse_analytics_datetime_bound(request.query_params.get("to"), end_of_day=True)

    qs = filtered_lobby_queryset(lobby_name=lobby_name, from_dt=from_dt, to_dt=to_dt)
    qs = annotate_lobby_metrics(qs)
    try:
        qs = apply_lobby_ordering(qs, "start_time")
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)

    lobbies = list(qs)
    snapshots = build_snapshots(lobbies)
    results = [lobby_instance_snapshot_to_dict(snapshots[lobby.uuid]) for lobby in lobbies if lobby.uuid in snapshots]
    return Response({"count": len(results), "results": results}, status=200)


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def get_lobby_instance(request, lobby_name="default"):
    """
    Lobby instance detail: analytics snapshot plus live proposal/participant breakdown.

    Query params:
    - lobby_uuid (optional): specific lobby instance. If omitted, resolves the
      active lobby for lobby_name, or the most recent finished one.
    """
    lobby_uuid_param = request.query_params.get("lobby_uuid", None)
    try:
        lobby = resolve_lobby_instance(lobby_name, lobby_uuid=lobby_uuid_param)
    except InvalidLobbyUuid:
        return Response({"error": "Invalid lobby_uuid"}, status=400)
    if lobby is None:
        return Response({"error": "Lobby not found"}, status=404)

    return Response(build_lobby_instance_detail(lobby), status=200)


api_urls = [
    path(
        "api/random_calls/analytics/lobbies",
        list_lobby_stats,
    ),
    path(
        "api/random_calls/analytics/lobbies/trends",
        list_lobby_trends,
    ),
    path(
        "api/random_calls/analytics/lobby/<str:lobby_name>/instance",
        get_lobby_instance,
    ),
]
