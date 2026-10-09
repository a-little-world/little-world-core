"""Canonical metric definitions for the ranged analytics graph."""

from management.analytics.core.time_series import MetricAggregation, MetricUnit, TimeSeriesMetric
from management.analytics.time_series import queries

METRICS: dict[str, TimeSeriesMetric] = {
    "video_calls": TimeSeriesMetric(
        metric_id="video_calls",
        display_name="Completed video calls",
        description="Completed calls in which both participants were active.",
        unit=MetricUnit.COUNT,
        aggregation=MetricAggregation.SUM,
        query=queries.video_call_count,
        supports_call_type=True,
    ),
    "user_signups": TimeSeriesMetric(
        metric_id="user_signups",
        display_name="User signups",
        description="Users registered in the selected date range.",
        unit=MetricUnit.COUNT,
        aggregation=MetricAggregation.SUM,
        query=queries.user_signups,
    ),
    "emails_sent": TimeSeriesMetric(
        metric_id="emails_sent",
        display_name="Emails sent",
        description="Successfully sent emails to accessible users.",
        unit=MetricUnit.COUNT,
        aggregation=MetricAggregation.SUM,
        query=queries.emails_sent,
    ),
    "dynamic_emails_sent": TimeSeriesMetric(
        metric_id="dynamic_emails_sent",
        display_name="Dynamic emails sent",
        description="Successfully sent dynamic emails to accessible users.",
        unit=MetricUnit.COUNT,
        aggregation=MetricAggregation.SUM,
        query=queries.dynamic_emails_sent,
    ),
    "user_sessions": TimeSeriesMetric(
        metric_id="user_sessions",
        display_name="User sessions (web, estimated)",
        description=(
            "Estimated web sessions started by accessible users. Excludes the native app "
            "(JWT logins create no session) and sessions ended by logging out."
        ),
        unit=MetricUnit.COUNT,
        aggregation=MetricAggregation.SUM,
        query=queries.user_sessions,
    ),
    "user_messages": TimeSeriesMetric(
        metric_id="user_messages",
        display_name="User messages",
        description="Messages between accessible users, excluding support conversations.",
        unit=MetricUnit.COUNT,
        aggregation=MetricAggregation.SUM,
        query=queries.user_messages,
    ),
    "video_call_total_duration": TimeSeriesMetric(
        metric_id="video_call_total_duration",
        display_name="Total video call time",
        description="Combined duration of completed calls in each period.",
        unit=MetricUnit.DURATION_SECONDS,
        aggregation=MetricAggregation.SUM,
        query=queries.video_call_duration,
        supports_call_type=True,
    ),
    "video_call_average_duration": TimeSeriesMetric(
        metric_id="video_call_average_duration",
        display_name="Average video call time",
        description="Average duration of completed calls in each period.",
        unit=MetricUnit.DURATION_SECONDS,
        aggregation=MetricAggregation.AVERAGE,
        query=queries.video_call_duration,
        supports_call_type=True,
    ),
}


def get_metric(metric_id: str) -> TimeSeriesMetric | None:
    return METRICS.get(metric_id)


def metric_metadata() -> list[dict]:
    return [metric.metadata() for metric in METRICS.values()]
