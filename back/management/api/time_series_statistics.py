from datetime import date

from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from management.analytics.core import display_time
from management.analytics.core.time_series import MetricUnit, build_time_series
from management.analytics.time_series.catalog import get_metric, metric_metadata
from management.helpers import IsAdminOrMatchingUser, get_accessible_users


class TimeSeriesRequestSerializer(serializers.Serializer):
    metric_id = serializers.CharField()
    start_date = serializers.DateField(default=date(2024, 1, 1))
    # Berlin "today", not the server's (UTC) date: matches how the range is bucketed.
    end_date = serializers.DateField(default=display_time.today)
    bucket_size = serializers.ChoiceField(choices=(1, 7, 30), default=1)
    call_type = serializers.ChoiceField(
        choices=("all", "standard", "random"),
        default="all",
    )

    def validate_metric_id(self, value):
        if get_metric(value) is None:
            raise serializers.ValidationError("Unknown time-series metric.")
        return value

    def validate(self, attrs):
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError({"end_date": "End date must be on or after start date."})
        return attrs


class TimeSeriesMetricSerializer(serializers.Serializer):
    id = serializers.CharField()
    display_name = serializers.CharField()
    description = serializers.CharField()
    unit = serializers.ChoiceField(choices=[unit.value for unit in MetricUnit])
    supports_call_type = serializers.BooleanField()


class TimeSeriesPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    period_value = serializers.FloatField()
    cumulative_value = serializers.FloatField()


class TimeSeriesResponseSerializer(serializers.Serializer):
    metric = TimeSeriesMetricSerializer()
    points = TimeSeriesPointSerializer(many=True)


@extend_schema(
    methods=["GET"],
    responses={200: TimeSeriesMetricSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    request=TimeSeriesRequestSerializer,
    responses={200: TimeSeriesResponseSerializer},
)
@api_view(["GET", "POST"])
@permission_classes([IsAdminOrMatchingUser])
def time_series_statistics(request):
    """List catalog metadata or calculate one metric over a date range."""
    if request.method == "GET":
        return Response(metric_metadata())

    serializer = TimeSeriesRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data
    metric = get_metric(params["metric_id"])

    points = build_time_series(
        metric,
        get_accessible_users(request.user),
        start_date=params["start_date"],
        end_date=params["end_date"],
        bucket_size=int(params["bucket_size"]),
        call_type=params["call_type"],
    )
    return Response({"metric": metric.metadata(), "points": points})


api_urls = [
    path(
        "api/matching/statistics/time-series/",
        time_series_statistics,
        name="time-series-statistics",
    ),
]
