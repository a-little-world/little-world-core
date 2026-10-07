from datetime import date, datetime, timedelta, timezone

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from video.models import LivekitSession

from management.analytics.core.display_time import DISPLAY_TIMEZONE
from management.analytics.core.time_series import (
    BucketAggregate,
    MetricAggregation,
    MetricUnit,
    TimeSeriesMetric,
    build_time_series,
)
from management.models.user import User


class TimeSeriesMachineryTests(SimpleTestCase):
    def test_sparse_periods_are_filled_and_cumulative_is_range_local(self):
        metric = TimeSeriesMetric(
            metric_id="test",
            display_name="Test",
            description="",
            unit=MetricUnit.COUNT,
            aggregation=MetricAggregation.SUM,
            query=lambda *_args, **_kwargs: {
                date(2026, 1, 1): BucketAggregate(total=2, count=2),
                date(2026, 1, 3): BucketAggregate(total=4, count=4),
            },
        )

        points = build_time_series(
            metric,
            User.objects.none(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
            bucket_size=1,
        )

        self.assertEqual(
            points,
            [
                {"date": "2026-01-01", "period_value": 2, "cumulative_value": 2},
                {"date": "2026-01-02", "period_value": 0, "cumulative_value": 2},
                {"date": "2026-01-03", "period_value": 4, "cumulative_value": 6},
            ],
        )

    def test_first_partial_bucket_is_labelled_with_start_date(self):
        metric = TimeSeriesMetric(
            metric_id="test_weekly",
            display_name="Test weekly",
            description="",
            unit=MetricUnit.COUNT,
            aggregation=MetricAggregation.SUM,
            query=lambda *_args, **_kwargs: {
                date(2026, 1, 5): BucketAggregate(total=3, count=3),
                date(2026, 1, 12): BucketAggregate(total=1, count=1),
            },
        )

        # 2026-01-07 is a Wednesday; its week bucket starts on Monday 2026-01-05.
        points = build_time_series(
            metric,
            User.objects.none(),
            start_date=date(2026, 1, 7),
            end_date=date(2026, 1, 14),
            bucket_size=7,
        )

        self.assertEqual([point["date"] for point in points], ["2026-01-07", "2026-01-12"])
        self.assertEqual(points[0]["period_value"], 3)

    def test_cumulative_average_is_weighted_by_call_count(self):
        metric = TimeSeriesMetric(
            metric_id="test_average",
            display_name="Test average",
            description="",
            unit=MetricUnit.DURATION_SECONDS,
            aggregation=MetricAggregation.AVERAGE,
            query=lambda *_args, **_kwargs: {
                date(2026, 1, 1): BucketAggregate(total=120, count=2),
                date(2026, 1, 2): BucketAggregate(total=180, count=1),
            },
        )

        points = build_time_series(
            metric,
            User.objects.none(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            bucket_size=1,
        )

        self.assertEqual(points[0]["period_value"], 60)
        self.assertEqual(points[1]["period_value"], 180)
        self.assertEqual(points[1]["cumulative_value"], 100)


class TimeSeriesStatisticsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email="time-series-admin@example.com",
            password="Test123!",
            first_name="Admin",
            last_name="User",
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.user1 = User.objects.create_user(
            email="time-series-user1@example.com",
            password="Test123!",
            first_name="First",
            last_name="User",
        )
        self.user2 = User.objects.create_user(
            email="time-series-user2@example.com",
            password="Test123!",
            first_name="Second",
            last_name="User",
        )
        self.client.force_authenticate(user=self.staff)

    def _call(self, *, started, minutes, random):
        session = LivekitSession.create_backdated(
            created_at=started,
            u1=self.user1,
            u2=self.user2,
            both_have_been_active=True,
            random_call_session=random,
            is_active=minutes is None,
            end_time=None if minutes is None else started + timedelta(minutes=minutes),
        )
        return session

    def _post(self, metric_id, call_type="all"):
        return self.client.post(
            "/api/matching/statistics/time-series/",
            {
                "metric_id": metric_id,
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
                "bucket_size": 1,
                "call_type": call_type,
            },
            format="json",
        )

    def test_catalog_is_served_by_the_backend(self):
        response = self.client.get("/api/matching/statistics/time-series/")

        self.assertEqual(response.status_code, 200)
        metrics = {metric["id"]: metric for metric in response.data}
        self.assertIn("video_calls", metrics)
        self.assertTrue(metrics["video_calls"]["supports_call_type"])
        self.assertEqual(
            metrics["video_call_total_duration"]["unit"],
            "duration_seconds",
        )

    def test_call_type_filters_count_and_fills_empty_days(self):
        started = datetime(2026, 1, 1, 12, tzinfo=DISPLAY_TIMEZONE)
        self._call(started=started, minutes=30, random=False)
        self._call(started=started + timedelta(hours=1), minutes=15, random=True)

        response = self._post("video_calls", call_type="standard")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["points"],
            [
                {"date": "2026-01-01", "period_value": 1.0, "cumulative_value": 1.0},
                {"date": "2026-01-02", "period_value": 0.0, "cumulative_value": 1.0},
            ],
        )

    def test_duration_values_are_seconds_and_cumulative(self):
        started = datetime(2026, 1, 1, 12, tzinfo=DISPLAY_TIMEZONE)
        self._call(started=started, minutes=30, random=False)
        self._call(started=started + timedelta(days=1), minutes=45, random=False)

        response = self._post("video_call_total_duration")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["points"][0]["period_value"], 1800)
        self.assertEqual(response.data["points"][1]["period_value"], 2700)
        self.assertEqual(response.data["points"][1]["cumulative_value"], 4500)

    def test_unfinished_calls_are_excluded_from_call_count(self):
        started = datetime(2026, 1, 1, 12, tzinfo=DISPLAY_TIMEZONE)
        self._call(started=started, minutes=30, random=False)
        self._call(started=started + timedelta(hours=1), minutes=None, random=False)

        response = self._post("video_calls")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["points"][0]["period_value"], 1)

    def test_buckets_use_the_display_timezone_not_utc(self):
        # 23:30 UTC on 1 Jan is already 00:30 on 2 Jan in Berlin, so the call must land
        # in the 2 Jan bucket rather than the UTC day it was stored under.
        self._call(
            started=datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc),
            minutes=30,
            random=False,
        )

        response = self._post("video_calls")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["points"],
            [
                {"date": "2026-01-01", "period_value": 0.0, "cumulative_value": 0.0},
                {"date": "2026-01-02", "period_value": 1.0, "cumulative_value": 1.0},
            ],
        )
