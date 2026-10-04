from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from management.api.user_advanced import (
    _serialize_user_match_previews,
    build_user_table_batch,
    get_match_waiting_time,
)
from management.models.matches import Match
from management.models.state import State
from management.models.unconfirmed_matches import ProposedMatch
from management.models.user import User


def _user(label: str) -> User:
    return User.objects.create_user(
        email=f"{label}-user-table@example.com",
        password="Test123!",
        first_name=label.title(),
        last_name="User",
    )


class UserTableBatchEquivalenceTests(TestCase):
    """build_user_table_batch must match the per-row serializers it replaces."""

    def setUp(self):
        self.searching = _user("searching")
        self.waiting_only = _user("waiting")
        self.partner = _user("partner")
        self.unconfirmed_partner = _user("unconfirmed")
        self.proposed_partner = _user("proposed")

        now = timezone.now()
        state = self.searching.state
        state.is_onboarded = True
        state.searching_state = State.SearchingStateChoices.SEARCHING
        state.onboarding_call_completed_at = now - timedelta(days=3)
        state.save()

        waiting_state = self.waiting_only.state
        waiting_state.is_onboarded = True
        waiting_state.searching_state = State.SearchingStateChoices.SEARCHING
        waiting_state.onboarding_call_completed_at = now - timedelta(days=5)
        waiting_state.save()

        confirmed = Match.objects.create(user1=self.searching, user2=self.partner)
        confirmed.confirmed_by.add(self.searching)
        Match.objects.create(user1=self.searching, user2=self.unconfirmed_partner)
        ProposedMatch.objects.create(user1=self.searching, user2=self.proposed_partner)

    def test_batch_matches_per_row_serialization(self):
        users = [self.searching, self.waiting_only]
        batch = build_user_table_batch(users)

        for user in users:
            self.assertEqual(batch["matches"][user.id], _serialize_user_match_previews(user))
            if user.id in batch["waiting_time"]:
                self.assertEqual(batch["waiting_time"][user.id], get_match_waiting_time(user))


class UserTableListApiTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.staff = _user("staff")
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.api_client.force_authenticate(user=self.staff)

    def test_list_profile_omits_interests_but_detail_includes_them(self):
        list_response = self.api_client.get("/api/matching/users/")
        self.assertEqual(list_response.status_code, 200)
        row = next(item for item in list_response.data["results"] if item["id"] == self.staff.id)
        self.assertNotIn("interests", row["profile"])
        self.assertIn("first_name", row["profile"])

        detail_response = self.api_client.get(f"/api/matching/users/{self.staff.id}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("interests", detail_response.data["profile"])

    def test_list_query_count_is_page_size_independent(self):
        for index in range(5):
            _user(f"extra{index}")

        def query_count(page_size: int) -> int:
            with CaptureQueriesContext(connection) as captured:
                response = self.api_client.get(f"/api/matching/users/?page_size={page_size}")
            self.assertEqual(response.status_code, 200)
            return len(captured)

        self.assertEqual(query_count(1), query_count(5))
