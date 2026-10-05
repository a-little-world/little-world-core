from datetime import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from management.analytics.core.display_time import DISPLAY_TIMEZONE
from management.models.profile import Profile
from management.models.user import User


class HighlightsStatisticsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email="highlights-admin@example.com",
            password="Test123!",
            first_name="Admin",
            last_name="User",
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.client.force_authenticate(user=self.staff)

    def _user(self, email, *, joined_at, user_type, onboarded):
        user = User.objects.create_user(
            email=email,
            password="Test123!",
            first_name="Highlight",
            last_name="User",
        )
        User.objects.filter(pk=user.pk).update(date_joined=joined_at)
        user.profile.user_type = user_type
        user.profile.save(update_fields=["user_type"])
        user.state.is_onboarded = onboarded
        user.state.save(update_fields=["is_onboarded"])
        return user

    def test_date_range_uses_signup_cohort_and_canonical_onboarded_stage(self):
        self._user(
            "included-learner@example.com",
            joined_at=datetime(2026, 1, 10, 12, tzinfo=DISPLAY_TIMEZONE),
            user_type=Profile.TypeChoices.LEARNER,
            onboarded=True,
        )
        self._user(
            "included-volunteer@example.com",
            joined_at=datetime(2026, 1, 20, 12, tzinfo=DISPLAY_TIMEZONE),
            user_type=Profile.TypeChoices.VOLUNTEER,
            onboarded=False,
        )
        self._user(
            "excluded@example.com",
            joined_at=datetime(2025, 12, 31, 12, tzinfo=DISPLAY_TIMEZONE),
            user_type=Profile.TypeChoices.LEARNER,
            onboarded=True,
        )

        response = self.client.post(
            "/api/matching/users/statistics/highlights/",
            {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["registrations"], 2)
        self.assertEqual(response.data["registered_learners"], 1)
        self.assertEqual(response.data["registered_volunteers"], 1)
        self.assertEqual(response.data["onboarded_learners"], 1)
        self.assertEqual(response.data["onboarded_volunteers"], 0)
        self.assertEqual(response.data["in_flight_matches"], 0)
        self.assertEqual(response.data["successful_matches"], 0)

    def test_rejects_an_inverted_date_range(self):
        response = self.client.post(
            "/api/matching/users/statistics/highlights/",
            {"start_date": "2026-02-01", "end_date": "2026-01-01"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("end_date", response.data)
