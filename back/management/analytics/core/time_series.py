"""Domain-agnostic machinery for bucketed analytics time series."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from django.db.models import QuerySet


class MetricUnit(StrEnum):
    COUNT = "count"
    DURATION_SECONDS = "duration_seconds"


class MetricAggregation(StrEnum):
    SUM = "sum"
    AVERAGE = "average"


@dataclass(frozen=True)
class BucketAggregate:
    total: float
    count: int


MetricQuery = Callable[..., dict[date, BucketAggregate]]


@dataclass(frozen=True)
class TimeSeriesMetric:
    metric_id: str
    display_name: str
    description: str
    unit: MetricUnit
    aggregation: MetricAggregation
    query: MetricQuery
    supports_call_type: bool = False

    def metadata(self) -> dict:
        return {
            "id": self.metric_id,
            "display_name": self.display_name,
            "description": self.description,
            "unit": self.unit.value,
            "supports_call_type": self.supports_call_type,
        }


def _first_bucket(value: date, bucket_size: int) -> date:
    if bucket_size == 1:
        return value
    if bucket_size == 7:
        return value - timedelta(days=value.weekday())
    if bucket_size == 30:
        return value.replace(day=1)
    raise ValueError("bucket_size must be one of 1, 7, or 30")


def _next_bucket(value: date, bucket_size: int) -> date:
    if bucket_size == 1:
        return value + timedelta(days=1)
    if bucket_size == 7:
        return value + timedelta(days=7)
    if bucket_size == 30:
        if value.month == 12:
            return value.replace(year=value.year + 1, month=1)
        return value.replace(month=value.month + 1)
    raise ValueError("bucket_size must be one of 1, 7, or 30")


def bucket_dates(start_date: date, end_date: date, bucket_size: int) -> list[date]:
    current = _first_bucket(start_date, bucket_size)
    final = _first_bucket(end_date, bucket_size)
    result = []
    while current <= final:
        result.append(current)
        current = _next_bucket(current, bucket_size)
    return result


def build_time_series(
    metric: TimeSeriesMetric,
    users: QuerySet,
    *,
    start_date: date,
    end_date: date,
    bucket_size: int,
    call_type: str = "all",
) -> list[dict]:
    """Fill sparse periods and calculate running values within the selected range."""
    aggregates = metric.query(
        users,
        start_date=start_date,
        end_date=end_date,
        bucket_size=bucket_size,
        call_type=call_type,
    )

    cumulative_total = 0.0
    cumulative_count = 0
    points = []
    for bucket in bucket_dates(start_date, end_date, bucket_size):
        aggregate = aggregates.get(bucket, BucketAggregate(total=0, count=0))
        cumulative_total += aggregate.total
        cumulative_count += aggregate.count

        if metric.aggregation is MetricAggregation.AVERAGE:
            period_value = aggregate.total / aggregate.count if aggregate.count else 0
            cumulative_value = cumulative_total / cumulative_count if cumulative_count else 0
        else:
            period_value = aggregate.total
            cumulative_value = cumulative_total

        # The first weekly/monthly bucket can start before the range; queries only count
        # from start_date, so label it with start_date rather than imply a full period.
        points.append(
            {
                "date": max(bucket, start_date).isoformat(),
                "period_value": round(period_value, 2),
                "cumulative_value": round(cumulative_value, 2),
            }
        )
    return points
