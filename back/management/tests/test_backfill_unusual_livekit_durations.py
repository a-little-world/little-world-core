"""unusual_length LivekitSession rows get a webhook end, or a 45-minute stamp."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from video.models import LiveKitRoom, LivekitSession, LivekitWebhookEvent
from video.services.livekit_session_correction import UNUSUAL_LENGTH_CUTOFF

from management.models.user import User


class BackfillUnusualLivekitDurationsTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user(email="dur-u1@test.de", password="x", first_name="One", last_name="A")
        self.u2 = User.objects.create_user(email="dur-u2@test.de", password="x", first_name="Two", last_name="B")
        self.room = LiveKitRoom.objects.create(u1=self.u1, u2=self.u2)

    def _session(self, *, start, end, **kwargs):
        defaults = {
            "room": self.room,
            "u1": self.u1,
            "u2": self.u2,
            "is_active": True,
            "u1_active": True,
            "u2_active": False,
            "both_have_been_active": True,
            "unusual_length": True,
        }
        defaults.update(kwargs)
        session = LivekitSession.objects.create(**defaults)
        LivekitSession.objects.filter(pk=session.pk).update(created_at=start, end_time=end)
        session.refresh_from_db()
        return session

    def _event(self, at, event_type):
        event = LivekitWebhookEvent.objects.create(data={"event": event_type})
        LivekitWebhookEvent.objects.filter(pk=event.pk).update(created_at=at)
        event.refresh_from_db()
        return event

    def test_dry_run_does_not_write(self):
        start = timezone.now() - timedelta(days=2)
        session = self._session(start=start, end=start + timedelta(hours=4))
        session.webhook_events.add(self._event(start + timedelta(minutes=34), "participant_left"))

        out = StringIO()
        call_command("backfill_unusual_livekit_durations", stdout=out)

        session.refresh_from_db()
        self.assertTrue(session.unusual_length)
        self.assertEqual(session.end_time, start + timedelta(hours=4))
        self.assertIn("Dry run", out.getvalue())

    def test_apply_uses_first_sitting_leave_and_ignores_a_later_week_leave(self):
        start = timezone.now() - timedelta(days=10)
        session = self._session(start=start, end=start + timedelta(days=7))
        first_leave = start + timedelta(minutes=34)
        session.webhook_events.add(self._event(start + timedelta(seconds=2), "participant_joined"))
        session.webhook_events.add(self._event(first_leave, "participant_left"))
        session.webhook_events.add(self._event(start + timedelta(days=7), "participant_left"))

        call_command("backfill_unusual_livekit_durations", "--apply")

        session.refresh_from_db()
        self.assertEqual(session.end_time, first_leave)
        self.assertFalse(session.unusual_length)
        self.assertFalse(session.is_active)
        self.assertFalse(session.u1_active)
        self.assertFalse(session.u2_active)

    def test_no_webhooks_stamps_45_minutes_and_stays_unusual(self):
        start = timezone.now() - timedelta(days=2)
        session = self._session(start=start, end=start + timedelta(hours=4))

        call_command("backfill_unusual_livekit_durations", "--apply")

        session.refresh_from_db()
        self.assertEqual(session.end_time, start + UNUSUAL_LENGTH_CUTOFF)
        self.assertTrue(session.unusual_length)
        self.assertFalse(session.is_active)

    def test_mutual_join_only_stamps_45_minutes(self):
        start = timezone.now() - timedelta(days=2)
        session = self._session(start=start, end=start + timedelta(hours=4), both_have_been_active=True)
        session.webhook_events.add(self._event(start + timedelta(seconds=1), "participant_joined"))
        session.webhook_events.add(self._event(start + timedelta(seconds=8), "participant_joined"))

        call_command("backfill_unusual_livekit_durations", "--apply")

        session.refresh_from_db()
        self.assertEqual(session.end_time, start + UNUSUAL_LENGTH_CUTOFF)
        self.assertTrue(session.unusual_length)
        self.assertFalse(session.is_active)

    def test_one_sided_join_only_uses_the_last_join(self):
        start = timezone.now() - timedelta(days=2)
        session = self._session(
            start=start,
            end=start + timedelta(hours=4),
            both_have_been_active=False,
            u1_was_active=True,
            u2_was_active=False,
        )
        last_join = start + timedelta(seconds=8)
        session.webhook_events.add(self._event(last_join, "participant_joined"))

        call_command("backfill_unusual_livekit_durations", "--apply")

        session.refresh_from_db()
        self.assertEqual(session.end_time, last_join)
        self.assertFalse(session.unusual_length)

    def test_one_sided_with_a_nearby_successful_sibling_ends_when_that_call_starts(self):
        start = timezone.now() - timedelta(days=2)
        leftover = self._session(
            start=start,
            end=start + timedelta(hours=4),
            both_have_been_active=False,
            u1_was_active=True,
            u2_was_active=False,
            u1_active=False,
            u2_active=False,
            is_active=False,
        )
        leftover.webhook_events.add(self._event(start + timedelta(seconds=1), "participant_joined"))
        sibling = LivekitSession.objects.create(
            room=self.room,
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
            unusual_length=False,
            u1_was_active=True,
            u2_was_active=True,
        )
        LivekitSession.objects.filter(pk=sibling.pk).update(
            created_at=start + timedelta(seconds=50), end_time=start + timedelta(minutes=13)
        )

        call_command("backfill_unusual_livekit_durations", "--apply")

        leftover.refresh_from_db()
        self.assertEqual(leftover.end_time, start + timedelta(seconds=50))
        self.assertTrue(leftover.unusual_length)
        self.assertFalse(leftover.both_have_been_active)

    def test_mutual_join_only_is_clipped_to_the_next_call_in_the_room(self):
        start = timezone.now() - timedelta(days=2)
        session = self._session(
            start=start,
            end=start + timedelta(hours=4),
            both_have_been_active=True,
            u1_active=False,
            u2_active=False,
            is_active=False,
        )
        session.webhook_events.add(self._event(start + timedelta(seconds=1), "participant_joined"))
        session.webhook_events.add(self._event(start + timedelta(seconds=8), "participant_joined"))
        later_start = start + timedelta(minutes=20)
        later = LivekitSession.objects.create(
            room=self.room,
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
            unusual_length=False,
            u1_was_active=True,
            u2_was_active=True,
        )
        LivekitSession.objects.filter(pk=later.pk).update(
            created_at=later_start, end_time=later_start + timedelta(minutes=15)
        )

        call_command("backfill_unusual_livekit_durations", "--apply")

        session.refresh_from_db()
        self.assertEqual(session.end_time, later_start)
        self.assertTrue(session.unusual_length)

    def test_one_sided_followed_by_a_call_within_45_minutes_ends_when_that_call_starts(self):
        start = timezone.now() - timedelta(days=2)
        missed = self._session(
            start=start,
            end=start + timedelta(hours=4),
            both_have_been_active=False,
            u1_was_active=True,
            u2_was_active=False,
            u1_active=False,
            u2_active=False,
            is_active=False,
        )
        missed.webhook_events.add(self._event(start + timedelta(seconds=2), "participant_joined"))
        later_start = start + timedelta(minutes=10)
        later = LivekitSession.objects.create(
            room=self.room,
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
            unusual_length=False,
            u1_was_active=True,
            u2_was_active=True,
        )
        LivekitSession.objects.filter(pk=later.pk).update(
            created_at=later_start, end_time=later_start + timedelta(minutes=10)
        )

        call_command("backfill_unusual_livekit_durations", "--apply")

        missed.refresh_from_db()
        self.assertEqual(missed.end_time, later_start)
        self.assertTrue(missed.unusual_length)

    def test_a_call_after_45_minutes_does_not_change_a_missed_ring(self):
        start = timezone.now() - timedelta(days=2)
        missed = self._session(
            start=start,
            end=start + timedelta(hours=4),
            both_have_been_active=False,
            u1_was_active=True,
            u2_was_active=False,
            u1_active=False,
            u2_active=False,
            is_active=False,
        )
        join_at = start + timedelta(seconds=2)
        missed.webhook_events.add(self._event(join_at, "participant_joined"))
        later = LivekitSession.objects.create(
            room=self.room,
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
            unusual_length=False,
            u1_was_active=True,
            u2_was_active=True,
        )
        LivekitSession.objects.filter(pk=later.pk).update(
            created_at=start + timedelta(minutes=50), end_time=start + timedelta(minutes=60)
        )

        call_command("backfill_unusual_livekit_durations", "--apply")

        missed.refresh_from_db()
        self.assertEqual(missed.end_time, join_at)
        self.assertFalse(missed.unusual_length)

    def test_a_60_minute_first_sitting_leave_is_kept_not_clipped_to_45(self):
        start = timezone.now() - timedelta(days=2)
        session = self._session(start=start, end=start + timedelta(hours=4))
        real_leave = start + timedelta(minutes=60)
        session.webhook_events.add(self._event(real_leave, "participant_left"))

        call_command("backfill_unusual_livekit_durations", "--apply")

        session.refresh_from_db()
        self.assertEqual(session.end_time, real_leave)
        self.assertFalse(session.unusual_length)

    def test_split_pair_leftover_is_skipped(self):
        start = timezone.now() - timedelta(days=1)
        leftover = self._session(
            start=start,
            end=start + timedelta(hours=4),
            both_have_been_active=False,
            u1_was_active=True,
            u2_was_active=False,
            u1_active=False,
            u2_active=False,
            is_active=False,
            first_active_user=self.u1,
        )
        real = LivekitSession.objects.create(
            room=self.room,
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=False,
            u1_was_active=False,
            u2_was_active=True,
            unusual_length=False,
            first_active_user=self.u2,
        )
        LivekitSession.objects.filter(pk=real.pk).update(
            created_at=start + timedelta(seconds=1), end_time=start + timedelta(minutes=37)
        )

        call_command("backfill_unusual_livekit_durations", "--apply")

        leftover.refresh_from_db()
        self.assertTrue(leftover.unusual_length)
        self.assertEqual(leftover.end_time, start + timedelta(hours=4))
