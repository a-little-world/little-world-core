from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from management.models.state import State
from management.models.user import User


class SearchingStateLastUpdatedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email=f"searching-state-{uuid4()}@example.com",
            password="Test123!",
            first_name="Search",
            last_name="User",
        )
        self.state = self.user.state
        self.stale = timezone.now() - timedelta(days=5)
        self.state.searching_state_last_updated = self.stale
        self.state.save(update_fields=["searching_state_last_updated"])

    def test_unrelated_state_save_does_not_bump_timestamp(self):
        self.state.unresponsive = True
        self.state.save()
        self.state.refresh_from_db()

        self.assertEqual(self.state.searching_state_last_updated, self.stale)

    def test_changing_searching_state_bumps_timestamp(self):
        self.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.state.save()
        self.state.refresh_from_db()

        self.assertGreater(self.state.searching_state_last_updated, self.stale)
        self.assertEqual(self.state.searching_state, State.SearchingStateChoices.SEARCHING)

    def test_update_fields_searching_state_also_persists_timestamp(self):
        self.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.state.save(update_fields=["searching_state"])
        self.state.refresh_from_db()

        self.assertGreater(self.state.searching_state_last_updated, self.stale)

    def test_change_searching_state_helper_bumps_timestamp(self):
        self.state.change_searching_state(State.SearchingStateChoices.SEARCHING)
        self.state.refresh_from_db()

        self.assertGreater(self.state.searching_state_last_updated, self.stale)

    def test_set_idle_bumps_timestamp(self):
        self.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.state.save(update_fields=["searching_state"])
        after_searching = self.state.searching_state_last_updated

        self.state.set_idle()
        self.state.refresh_from_db()

        self.assertGreater(self.state.searching_state_last_updated, after_searching)
        self.assertEqual(self.state.searching_state, State.SearchingStateChoices.IDLE)
