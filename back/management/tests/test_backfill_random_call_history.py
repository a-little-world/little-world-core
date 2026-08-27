"""The backfill fills e-mail triggers, so its guards are the thing worth testing.

On 2026-08-27 a production run of this command put 110 journey e-mails into people's
inboxes in a single task run — one person received eleven — because filling
``first_interaction_at`` drops a pair straight into the no-video-call ladder, and m042 has
no upper bound. The command had no tests at all.
"""

from datetime import timedelta
from uuid import uuid4

from chat.models import Chat, Message
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone as dj_timezone

from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType
from management.models.user import User
from management.tasks import automatic_emails_m031_m032_m033_m042


def _user(label: str) -> User:
    return User.objects.create_user(
        email=f"{label}-{uuid4()}@example.com",
        password="Test123!",
        first_name="Test",
        last_name=label,
    )


class BackfillRandomCallHistoryTests(TestCase):
    def _pair_with_lobby_chat(self, *, days_ago: int) -> Match:
        """A Random Call match whose only history is a two-way lobby chat, and no call."""
        user1, user2 = _user("rc-a"), _user("rc-b")
        chat = Chat.objects.create(u1=user1, u2=user2)
        first = Message.objects.create(chat=chat, sender=user1, recipient=user2, text="Hallo")
        second = Message.objects.create(chat=chat, sender=user2, recipient=user1, text="Hi")
        when = dj_timezone.now() - timedelta(days=days_ago)
        Message.objects.filter(pk__in=[first.pk, second.pk]).update(created=when)

        return Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.RANDOM_CALL,
            active=True,
            confirmed=True,
            total_mutal_video_calls_counter=0,
        )

    def test_fills_first_interaction_from_lobby_history(self):
        match = self._pair_with_lobby_chat(days_ago=40)
        self.assertIsNone(match.first_interaction_at)

        call_command("backfill_random_call_history", "--apply")

        match.refresh_from_db()
        self.assertIsNotNone(match.first_interaction_at)
        self.assertEqual(match.total_messages_counter, 2)

    def test_guard_suppresses_the_retroactive_ladder(self):
        """A 40-day-old lobby chat must not trigger "no video call in 30 days" on backfill."""
        match = self._pair_with_lobby_chat(days_ago=40)

        call_command("backfill_random_call_history", "--apply")

        match.refresh_from_db()
        self.assertTrue(match.auto_email_m042_send)
        self.assertNotIn(str(match.uuid), automatic_emails_m031_m032_m033_m042()["matches_m042"])

    def test_allow_journey_emails_lets_them_through(self):
        match = self._pair_with_lobby_chat(days_ago=40)

        call_command("backfill_random_call_history", "--apply", "--allow-journey-emails")

        match.refresh_from_db()
        self.assertFalse(match.auto_email_m042_send)
        self.assertIn(str(match.uuid), automatic_emails_m031_m032_m033_m042()["matches_m042"])

    def test_only_passed_stages_are_armed_so_the_ladder_continues(self):
        """A 10-day-old chat has passed m031 only; m032 must still fire on day 14."""
        match = self._pair_with_lobby_chat(days_ago=10)

        call_command("backfill_random_call_history", "--apply")

        match.refresh_from_db()
        self.assertTrue(match.auto_email_m031_send)
        self.assertFalse(match.auto_email_m032_send)
        self.assertFalse(match.auto_email_m033_send)
        self.assertFalse(match.auto_email_m042_send)

    def test_a_match_that_already_had_first_interaction_is_left_alone(self):
        """Its flags already record what it has been sent; re-arming would silence it."""
        match = self._pair_with_lobby_chat(days_ago=40)
        Match.objects.filter(pk=match.pk).update(first_interaction_at=dj_timezone.now() - timedelta(days=40))

        call_command("backfill_random_call_history", "--apply")

        match.refresh_from_db()
        self.assertFalse(match.auto_email_m042_send)

    def test_dry_run_writes_nothing(self):
        match = self._pair_with_lobby_chat(days_ago=40)

        call_command("backfill_random_call_history")

        match.refresh_from_db()
        self.assertIsNone(match.first_interaction_at)
        self.assertFalse(match.auto_email_m042_send)
