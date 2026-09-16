"""Stuck LivekitSession rows are closed and stamped at 45 minutes, not recapped if they ended normally."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from management.models.user import User

from video.models import LiveKitRoom, LivekitSession
from video.services.livekit_session_correction import UNUSUAL_LENGTH_CUTOFF, process_unusually_long_sessions


class UnusuallyLongSessionCorrectionTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user(email="cap-u1@test.de", password="x", first_name="One", last_name="A")
        self.u2 = User.objects.create_user(email="cap-u2@test.de", password="x", first_name="Two", last_name="B")
        self.room = LiveKitRoom.objects.create(u1=self.u1, u2=self.u2)

    def _session(self, *, created_ago, **kwargs):
        defaults = {
            "room": self.room,
            "u1": self.u1,
            "u2": self.u2,
            "is_active": True,
            "u1_active": True,
            "u2_active": True,
            "both_have_been_active": True,
        }
        defaults.update(kwargs)
        session = LivekitSession.objects.create(**defaults)
        start = timezone.now() - created_ago
        LivekitSession.objects.filter(pk=session.pk).update(created_at=start, end_time=kwargs.get("end_time"))
        session.refresh_from_db()
        return session

    def test_stuck_open_session_is_closed_and_stamped_at_45_minutes(self):
        session = self._session(created_ago=timedelta(days=2), end_time=None)

        result = process_unusually_long_sessions()

        session.refresh_from_db()
        self.assertEqual(result["updated"], 1)
        self.assertTrue(session.unusual_length)
        self.assertFalse(session.is_active)
        self.assertFalse(session.u1_active)
        self.assertFalse(session.u2_active)
        self.assertEqual(session.end_time, session.created_at + UNUSUAL_LENGTH_CUTOFF)
        self.assertIn("end_time=None", session.start_end_before_correction)

    def test_old_4h_unusual_stamp_is_recapped_to_45_minutes(self):
        session = self._session(created_ago=timedelta(days=2), is_active=False, u1_active=False, u2_active=False)
        four_h_end = session.created_at + timedelta(hours=4)
        LivekitSession.objects.filter(pk=session.pk).update(
            unusual_length=True, end_time=four_h_end, is_active=False, u1_active=False, u2_active=False
        )

        process_unusually_long_sessions()

        session.refresh_from_db()
        self.assertEqual(session.end_time, session.created_at + UNUSUAL_LENGTH_CUTOFF)
        self.assertTrue(session.unusual_length)
        self.assertFalse(session.is_active)

    def test_finished_90_minute_call_is_not_recapped(self):
        session = self._session(created_ago=timedelta(days=2), is_active=False, u1_active=False, u2_active=False)
        real_end = session.created_at + timedelta(minutes=90)
        LivekitSession.objects.filter(pk=session.pk).update(
            unusual_length=False, end_time=real_end, is_active=False, u1_active=False, u2_active=False
        )

        result = process_unusually_long_sessions()

        session.refresh_from_db()
        self.assertEqual(result["updated"], 0)
        self.assertFalse(session.unusual_length)
        self.assertEqual(session.end_time, real_end)

    def test_min_age_skips_a_live_call_that_started_an_hour_ago(self):
        session = self._session(created_ago=timedelta(hours=1), end_time=None)

        result = process_unusually_long_sessions(min_age_hours=24.0)

        session.refresh_from_db()
        self.assertEqual(result["updated"], 0)
        self.assertTrue(session.is_active)
        self.assertFalse(session.unusual_length)
        self.assertIsNone(session.end_time)
