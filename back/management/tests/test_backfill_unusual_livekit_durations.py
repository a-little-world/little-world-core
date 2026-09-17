"""unusual_length LivekitSession rows get a webhook end, or a 45-minute stamp."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from video.models import LiveKitRoom, LivekitSession, LivekitWebhookEvent
from video.services.livekit_session_correction import UNUSUAL_LENGTH_CUTOFF

from management.models.user import User


class _DurationBackfillHelpers:
    """Shared fixtures/helpers, not itself a TestCase so it contributes no test methods."""

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

    def _event(self, at, event_type, user=None):
        data = {"event": event_type}
        if user is not None:
            data["participant"] = {"identity": str(user.uuid)}
        event = LivekitWebhookEvent.objects.create(data=data)
        LivekitWebhookEvent.objects.filter(pk=event.pk).update(created_at=at)
        event.refresh_from_db()
        return event


class BackfillUnusualLivekitDurationsTests(_DurationBackfillHelpers, TestCase):
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


class LaterSittingReconstructionTests(_DurationBackfillHelpers, TestCase):
    """A row reused before the join-lock fix can carry a real, later call's webhooks
    glued onto the same session. Those should become their own visible session."""

    def test_a_glued_mutual_call_with_a_hangup_becomes_its_own_row(self):
        start = timezone.now() - timedelta(days=10)
        session = self._session(start=start, end=start + timedelta(hours=4))
        session.webhook_events.add(self._event(start + timedelta(minutes=34), "participant_left", self.u1))

        later_start = start + timedelta(days=7)
        later_leave = later_start + timedelta(minutes=12)
        session.webhook_events.add(self._event(later_start, "participant_joined", self.u1))
        session.webhook_events.add(self._event(later_start + timedelta(seconds=2), "participant_joined", self.u2))
        session.webhook_events.add(self._event(later_leave, "participant_left", self.u2))

        call_command("backfill_unusual_livekit_durations", "--apply")

        session.refresh_from_db()
        self.assertEqual(session.end_time, start + timedelta(minutes=34))
        self.assertFalse(session.unusual_length)

        later = LivekitSession.objects.exclude(pk=session.pk).get(room=self.room)
        self.assertEqual(later.created_at, later_start)
        self.assertEqual(later.end_time, later_leave)
        self.assertTrue(later.both_have_been_active)
        self.assertFalse(later.unusual_length)
        self.assertEqual(later.u1_id, self.u1.pk)
        self.assertEqual(later.u2_id, self.u2.pk)
        self.assertEqual(later.webhook_events.count(), 3)
        self.assertEqual(
            {e.data.get("event") for e in session.webhook_events.all()},
            {"participant_left"},
        )

    def test_a_glued_mutual_call_with_no_hangup_is_stamped_and_clipped(self):
        start = timezone.now() - timedelta(days=10)
        session = self._session(start=start, end=start + timedelta(hours=4))
        session.webhook_events.add(self._event(start + timedelta(minutes=34), "participant_left", self.u1))

        later_start = start + timedelta(days=7)
        session.webhook_events.add(self._event(later_start, "participant_joined", self.u1))
        session.webhook_events.add(self._event(later_start + timedelta(seconds=2), "participant_joined", self.u2))

        call_command("backfill_unusual_livekit_durations", "--apply")

        later = LivekitSession.objects.exclude(pk=session.pk).get(room=self.room)
        self.assertEqual(later.created_at, later_start)
        self.assertEqual(later.end_time, later_start + UNUSUAL_LENGTH_CUTOFF)
        self.assertTrue(later.both_have_been_active)
        self.assertTrue(later.unusual_length)

    def test_a_glued_one_sided_join_becomes_a_zero_length_row(self):
        start = timezone.now() - timedelta(days=10)
        session = self._session(start=start, end=start + timedelta(hours=4))
        session.webhook_events.add(self._event(start + timedelta(minutes=34), "participant_left", self.u1))

        later_join = start + timedelta(days=7)
        session.webhook_events.add(self._event(later_join, "participant_joined", self.u1))

        call_command("backfill_unusual_livekit_durations", "--apply")

        later = LivekitSession.objects.exclude(pk=session.pk).get(room=self.room)
        self.assertEqual(later.created_at, later_join)
        self.assertEqual(later.end_time, later_join)
        self.assertFalse(later.both_have_been_active)
        self.assertFalse(later.unusual_length)

    def test_two_later_sittings_each_become_their_own_row(self):
        start = timezone.now() - timedelta(days=20)
        session = self._session(start=start, end=start + timedelta(hours=4))
        session.webhook_events.add(self._event(start + timedelta(minutes=34), "participant_left", self.u1))

        week1 = start + timedelta(days=7)
        session.webhook_events.add(self._event(week1, "participant_joined", self.u1))
        session.webhook_events.add(self._event(week1 + timedelta(minutes=10), "participant_left", self.u1))

        week2 = start + timedelta(days=14)
        session.webhook_events.add(self._event(week2, "participant_joined", self.u2))
        session.webhook_events.add(self._event(week2 + timedelta(minutes=5), "participant_left", self.u2))

        call_command("backfill_unusual_livekit_durations", "--apply")

        later_rows = LivekitSession.objects.exclude(pk=session.pk).filter(room=self.room).order_by("created_at")
        self.assertEqual(later_rows.count(), 2)
        self.assertEqual(later_rows[0].created_at, week1)
        self.assertEqual(later_rows[0].end_time, week1 + timedelta(minutes=10))
        self.assertEqual(later_rows[1].created_at, week2)
        self.assertEqual(later_rows[1].end_time, week2 + timedelta(minutes=5))

    def test_dry_run_does_not_create_a_row(self):
        start = timezone.now() - timedelta(days=10)
        session = self._session(start=start, end=start + timedelta(hours=4))
        session.webhook_events.add(self._event(start + timedelta(minutes=34), "participant_left", self.u1))
        later_start = start + timedelta(days=7)
        session.webhook_events.add(self._event(later_start, "participant_joined", self.u1))
        session.webhook_events.add(self._event(later_start + timedelta(seconds=2), "participant_joined", self.u2))

        out = StringIO()
        call_command("backfill_unusual_livekit_durations", stdout=out)

        self.assertEqual(LivekitSession.objects.filter(room=self.room).count(), 1)
        self.assertIn("later sittings recovered as new rows 1", out.getvalue())

    def test_an_unattributable_later_event_is_not_reconstructed(self):
        start = timezone.now() - timedelta(days=10)
        session = self._session(start=start, end=start + timedelta(hours=4))
        session.webhook_events.add(self._event(start + timedelta(minutes=34), "participant_left", self.u1))

        stranger = User.objects.create_user(email="stranger@test.de", password="x", first_name="Stray", last_name="C")
        later_start = start + timedelta(days=7)
        session.webhook_events.add(self._event(later_start, "participant_joined", stranger))

        call_command("backfill_unusual_livekit_durations", "--apply")

        self.assertEqual(LivekitSession.objects.filter(room=self.room).count(), 1)
