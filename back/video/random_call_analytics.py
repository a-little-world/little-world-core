from datetime import datetime, timedelta

from django.urls import path
from django.utils import timezone
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
from video.analytics.totals import build_lobby_range_totals, lobby_range_totals_to_dict
from video.lobby_resolution import InvalidLobbyUuid, resolve_lobby_instance

# Bounds the unpaginated trends response. The FE asks for 90 days; a year is the widest
# useful comparison and keeps an omitted or absurd range from returning every lobby ever.
MAX_TRENDS_RANGE_DAYS = 366


def clamp_trends_range(
    from_dt: datetime | None,
    to_dt: datetime | None,
    *,
    as_of: datetime,
) -> tuple[datetime, datetime | None]:
    """Bound the (open-ended) trends window to ``MAX_TRENDS_RANGE_DAYS``, anchored on its end."""
    end = to_dt or as_of
    earliest = end - timedelta(days=MAX_TRENDS_RANGE_DAYS)
    if from_dt is None or from_dt < earliest:
        return earliest, to_dt
    return from_dt, to_dt


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def list_lobby_stats(request):
    """Paginated lobby instance snapshots.

    Filters: ``lobby_name`` (unfiltered when absent), ``from``/``to`` — lobbies whose
    ``start_time`` falls within the range — and ``ordering`` from the allow-list.
    """
    as_of = timezone.now()
    lobby_name = request.query_params.get("lobby_name")
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

    snapshots = build_snapshots(page, as_of=as_of)
    results = [lobby_instance_snapshot_to_dict(snapshots[lobby.uuid]) for lobby in page if lobby.uuid in snapshots]
    return paginator.get_paginated_response(results)


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAdminOrMatchingUser])
def list_lobby_trends(request):
    """Chronological lobby instance snapshots for trend charts.

    Unpaginated by design — a trend line needs every point in the range at once.
    ``{"count": int, "results": [snapshot, ...], "totals": {...}}``, where ``results``
    carries the same snapshot shape as ``list_lobby_stats``, ordered oldest first, and
    ``totals`` aggregates the whole range (see ``LobbyRangeTotals``).

    Filters: ``lobby_name`` (unfiltered when absent) and ``from``/``to`` — lobbies whose
    ``start_time`` falls within the range, capped at ``MAX_TRENDS_RANGE_DAYS``.
    """
    as_of = timezone.now()
    lobby_name = request.query_params.get("lobby_name")
    from_dt = parse_analytics_datetime_bound(request.query_params.get("from"))
    to_dt = parse_analytics_datetime_bound(request.query_params.get("to"), end_of_day=True)

    from_dt, to_dt = clamp_trends_range(from_dt, to_dt, as_of=as_of)

    qs = filtered_lobby_queryset(lobby_name=lobby_name, from_dt=from_dt, to_dt=to_dt)
    qs = annotate_lobby_metrics(qs)
    qs = apply_lobby_ordering(qs, "start_time")

    lobbies = list(qs)
    snapshots = build_snapshots(lobbies, as_of=as_of)
    results = [lobby_instance_snapshot_to_dict(snapshots[lobby.uuid]) for lobby in lobbies if lobby.uuid in snapshots]
    totals = build_lobby_range_totals(lobbies, snapshots=snapshots)
    return Response(
        {
            "count": len(results),
            "results": results,
            "totals": lobby_range_totals_to_dict(totals),
        },
        status=200,
    )


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
