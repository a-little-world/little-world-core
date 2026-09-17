"""Split LivekitSession pairs from the join race become one both-active row."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from video.models import LiveKitRoom, LivekitSession, LivekitWebhookEvent

from management.models.user import User


class BackfillSplitLivekitSessionsTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user(email="split-u1@test.de", password="x", first_name="One", last_name="A")
        self.u2 = User.objects.create_user(email="split-u2@test.de", password="x", first_name="Two", last_name="B")
        self.room = LiveKitRoom.objects.create(u1=self.u1, u2=self.u2)

    def _session(self, **kwargs):
        defaults = {
            "room": self.room,
            "u1": self.u1,
            "u2": self.u2,
            "is_active": False,
            "both_have_been_active": False,
        }
        defaults.update(kwargs)
        return LivekitSession.objects.create(**defaults)

    def _split_pair(self, *, gap=timedelta(seconds=1.3)):
        start = timezone.now() - timedelta(days=1)
        leftover = self._session(
            u1_was_active=True,
            u1_active=False,
            u2_was_active=False,
            unusual_length=True,
            first_active_user=self.u1,
            random_call_session=True,
        )
        real = self._session(
            u1_was_active=False,
            u2_was_active=True,
            u2_active=False,
            unusual_length=False,
            first_active_user=self.u2,
            random_call_session=True,
        )
        leftover_end = start + timedelta(hours=4)
        real_end = start + timedelta(minutes=37)
        LivekitSession.objects.filter(pk=leftover.pk).update(created_at=start, end_time=leftover_end)
        LivekitSession.objects.filter(pk=real.pk).update(created_at=start + gap, end_time=real_end)
        leftover.refresh_from_db()
        real.refresh_from_db()
        return leftover, real

    def test_dry_run_does_not_write(self):
        leftover, real = self._split_pair()
        out = StringIO()
        call_command("backfill_split_livekit_sessions", stdout=out)

        self.assertEqual(LivekitSession.objects.filter(pk__in=[leftover.pk, real.pk]).count(), 2)
        leftover.refresh_from_db()
        real.refresh_from_db()
        self.assertFalse(leftover.both_have_been_active)
        self.assertFalse(real.both_have_been_active)
        self.assertIn("Dry run", out.getvalue())
        self.assertIn("split pairs found", out.getvalue())

    def test_apply_keeps_the_real_duration_row_and_drops_the_capped_one(self):
        leftover, real = self._split_pair()
        leftover_join = LivekitWebhookEvent.objects.create(data={"event": "participant_joined", "who": "u1"})
        real_join = LivekitWebhookEvent.objects.create(data={"event": "participant_joined", "who": "u2"})
        leftover.webhook_events.add(leftover_join)
        real.webhook_events.add(real_join)
        leftover_id = leftover.pk
        real_start = leftover.created_at
        real_end = real.end_time

        call_command("backfill_split_livekit_sessions", "--apply")

        self.assertFalse(LivekitSession.objects.filter(pk=leftover_id).exists())
        merged = LivekitSession.objects.get(pk=real.pk)
        self.assertTrue(merged.both_have_been_active)
        self.assertTrue(merged.u1_was_active)
        self.assertTrue(merged.u2_was_active)
        self.assertFalse(merged.is_active)
        self.assertFalse(merged.unusual_length)
        self.assertEqual(merged.created_at, real_start)
        self.assertEqual(merged.end_time, real_end)
        self.assertEqual(merged.first_active_user_id, self.u1.pk)
        self.assertEqual(set(merged.webhook_events.all()), {leftover_join, real_join})

    def test_far_apart_one_sided_sessions_are_not_merged(self):
        self._split_pair(gap=timedelta(minutes=10))

        call_command("backfill_split_livekit_sessions", "--apply")

        self.assertEqual(LivekitSession.objects.filter(room=self.room).count(), 2)
        self.assertFalse(LivekitSession.objects.filter(room=self.room, both_have_been_active=True).exists())

    def test_a_20s_capped_split_is_merged(self):
        leftover, real = self._split_pair(gap=timedelta(seconds=20))

        call_command("backfill_split_livekit_sessions", "--apply")

        self.assertFalse(LivekitSession.objects.filter(pk=leftover.pk).exists())
        merged = LivekitSession.objects.get(pk=real.pk)
        self.assertTrue(merged.both_have_been_active)

    def test_sequential_missed_calls_without_a_4h_leftover_are_not_merged(self):
        start = timezone.now() - timedelta(days=1)
        first = self._session(u1_was_active=True, u2_was_active=False, unusual_length=False, first_active_user=self.u1)
        second = self._session(u1_was_active=False, u2_was_active=True, unusual_length=False, first_active_user=self.u2)
        LivekitSession.objects.filter(pk=first.pk).update(created_at=start, end_time=start + timedelta(seconds=4))
        LivekitSession.objects.filter(pk=second.pk).update(
            created_at=start + timedelta(seconds=10), end_time=start + timedelta(seconds=40)
        )

        call_command("backfill_split_livekit_sessions", "--apply")

        self.assertEqual(LivekitSession.objects.filter(room=self.room).count(), 2)
        self.assertFalse(LivekitSession.objects.filter(room=self.room, both_have_been_active=True).exists())
