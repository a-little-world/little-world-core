"""Matching quality KPIs and pie: driven by match_success, not V2 finished buckets."""

from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from video.models import LivekitSession

from management.api.user_advanced_statistics import (
    kpi_dashboard_statistics_matching,
    match_quality_statistics,
)
from management.match_success import get_version, successful_matches
from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType
from management.models.user import User


def _user(label: str) -> User:
    return User.objects.create_user(
        email=f"{label}-{uuid4()}@example.com",
        password="Test123!",
        first_name="Test",
        last_name=label,
    )


def _add_call(match: Match, minutes: float) -> None:
    started = match.created_at + timedelta(hours=1)
    session = LivekitSession.objects.create(u1=match.user1, u2=match.user2, both_have_been_active=True)
    LivekitSession.objects.filter(pk=session.pk).update(
        created_at=started, end_time=started + timedelta(minutes=minutes)
    )


class MatchingQualitySuccessDrivenTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.staff = _user("kpi-staff")
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])

        self.unsuccessful = Match.objects.create(user1=_user("u-a"), user2=_user("u-b"))
        self.off_platform = Match.objects.create(
            user1=_user("u-c"),
            user2=_user("u-d"),
            completed_off_plattform=True,
        )
        self.legacy_completed_flag = Match.objects.create(
            user1=_user("u-e"),
            user2=_user("u-f"),
            completed=True,
        )
        self.support = Match.objects.create(
            user1=_user("u-g"),
            user2=_user("u-h"),
            support_matching=True,
        )
        self.temporary = Match.objects.create(
            user1=_user("u-i"),
            user2=_user("u-j"),
            match_type=MatchType.TEMPORARY,
        )

        version = get_version()
        assert version.details.get("success_minutes") is not None
        _add_call(self.unsuccessful, minutes=30)
        self.token_success = Match.objects.create(user1=_user("u-k"), user2=_user("u-l"))
        _add_call(self.token_success, minutes=version.details["success_minutes"])

    def _kpi(self):
        request = self.factory.get("/api/matching/users/statistics/kpi_matching/")
        force_authenticate(request, user=self.staff)
        return kpi_dashboard_statistics_matching(request)

    def test_kpi_uses_the_active_match_success_version(self):
        version = get_version()
        response = self._kpi()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["success_version_id"], version.id)
        self.assertEqual(response.data["success_version_title"], version.title)
        self.assertEqual(response.data["success_token_threshold"], version.success_token_threshold)

    def test_kpi_counts_success_from_successful_matches_not_completed_flag(self):
        journey = Match.journey(Match.objects.all())
        expected_successful = successful_matches(journey).count()
        expected_total = journey.count()

        response = self._kpi()
        self.assertEqual(response.data["successful_matches"], expected_successful)
        self.assertEqual(response.data["total_matches"], expected_total)
        self.assertEqual(
            response.data["successful_matches_percentage"], round(expected_successful / expected_total * 100, 2)
        )

        self.assertIn(self.off_platform.pk, successful_matches(journey).values_list("id", flat=True))
        self.assertIn(self.token_success.pk, successful_matches(journey).values_list("id", flat=True))
        self.assertNotIn(self.legacy_completed_flag.pk, successful_matches(journey).values_list("id", flat=True))
        self.assertNotIn(self.support.pk, journey.values_list("id", flat=True))
        self.assertNotIn(self.temporary.pk, journey.values_list("id", flat=True))

    def test_kpi_6_12_week_cohort_uses_the_same_success_rule(self):
        eight_weeks_ago = timezone.now() - timedelta(weeks=8)
        Match.objects.filter(pk=self.off_platform.pk).update(created_at=eight_weeks_ago)
        Match.objects.filter(pk=self.legacy_completed_flag.pk).update(created_at=eight_weeks_ago)

        response = self._kpi()
        self.assertEqual(response.data["matches_started_6_12_weeks_ago"], 2)
        self.assertEqual(response.data["matches_6_12_weeks_ago_successful"], 1)
        self.assertEqual(response.data["matches_6_12_weeks_ago_successful_percentage"], 50.0)

    def test_quality_pie_distribution_is_success_driven(self):
        request = self.factory.post(
            "/api/matching/users/statistics/match_quality/",
            {"start_date": "2021-01-01", "end_date": timezone.now().date().isoformat()},
            format="json",
        )
        force_authenticate(request, user=self.staff)
        response = match_quality_statistics(request)
        self.assertEqual(response.status_code, 200)

        version = get_version()
        self.assertEqual(response.data["success_version_id"], version.id)

        by_id = {slice["id"]: slice["count"] for slice in response.data["distribution"]}
        self.assertEqual(by_id["successful"], successful_matches(Match.journey()).count())
        self.assertEqual(sum(by_id.values()), response.data["total_matches"])
        self.assertNotIn("finished-matching", by_id)
        self.assertNotIn("match_journey_v2__completed_match", by_id)
