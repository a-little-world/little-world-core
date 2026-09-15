"""Concurrent LiveKit joins must share one session, not split a successful call."""

from unittest.mock import Mock, patch

from django.db import IntegrityError
from django.test import TestCase
from management.models.user import User

from video.livekit_webhook import (
    _get_or_create_active_session,
    process_webhook_classic_call__participant_joined,
    process_webhook_classic_call__participant_left,
    process_webhook_random_call__participant_joined,
)
from video.models import LiveKitRoom, LivekitSession, LivekitWebhookEvent


def _users_and_room(*, random_call_room=False):
    u1 = User.objects.create_user(email="u1-join@test.de", password="x", first_name="One", last_name="A")
    u2 = User.objects.create_user(email="u2-join@test.de", password="x", first_name="Two", last_name="B")
    room = LiveKitRoom.objects.create(u1=u1, u2=u2, random_call_room=random_call_room)
    return u1, u2, room


class SequentialJoinTests(TestCase):
    def setUp(self):
        self.u1, self.u2, self.room = _users_and_room()
        self.event = LivekitWebhookEvent.objects.create(data={})

    def _classic_join(self, user):
        with (
            patch("video.livekit_webhook.NewActiveCallRoom"),
            patch("video.livekit_webhook.push_notification_background"),
        ):
            process_webhook_classic_call__participant_joined(
                {}, self.event, str(user.uuid), user, str(self.room.uuid), self.room
            )

    def _classic_leave(self, user):
        with patch("video.livekit_webhook.InBlockIncomingCall"):
            process_webhook_classic_call__participant_left(
                {}, LivekitWebhookEvent.objects.create(data={}), str(user.uuid), user, str(self.room.uuid), self.room
            )

    def test_both_joins_share_one_session_and_mark_it_mutual(self):
        self._classic_join(self.u1)
        self._classic_join(self.u2)

        sessions = list(LivekitSession.objects.filter(room=self.room))
        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertTrue(session.both_have_been_active)
        self.assertTrue(session.u1_was_active)
        self.assertTrue(session.u2_was_active)
        self.assertTrue(session.is_active)

    def test_a_later_call_in_the_same_room_starts_a_new_session(self):
        self._classic_join(self.u1)
        self._classic_join(self.u2)
        self._classic_leave(self.u1)
        self._classic_leave(self.u2)
        self._classic_join(self.u1)

        sessions = list(LivekitSession.objects.filter(room=self.room).order_by("created_at"))
        self.assertEqual(len(sessions), 2)
        self.assertFalse(sessions[0].is_active)
        self.assertTrue(sessions[1].is_active)
        self.assertTrue(sessions[0].both_have_been_active)
        self.assertFalse(sessions[1].both_have_been_active)

    def test_room_cannot_have_two_active_sessions(self):
        LivekitSession.objects.create(room=self.room, u1=self.u1, u2=self.u2, is_active=True)
        with self.assertRaises(IntegrityError):
            LivekitSession.objects.create(room=self.room, u1=self.u1, u2=self.u2, is_active=True)

    def test_lost_create_race_attaches_to_the_winning_session(self):
        winner = LivekitSession.objects.create(
            room=self.room,
            u1=self.u1,
            u2=self.u2,
            is_active=True,
            u1_active=True,
            u1_was_active=True,
            first_active_user=self.u1,
        )
        qs = Mock()
        qs.first.side_effect = [None, winner]

        with (
            patch("video.livekit_webhook._lock_room"),
            patch("video.livekit_webhook._active_sessions", return_value=qs),
            patch("video.livekit_webhook._create_join_session", side_effect=IntegrityError()),
        ):
            session, already_mutual = _get_or_create_active_session(self.room, self.u2, random_call_session=False)

        winner.refresh_from_db()
        self.assertEqual(session.pk, winner.pk)
        self.assertFalse(already_mutual)
        self.assertTrue(winner.both_have_been_active)
        self.assertTrue(winner.u2_was_active)


class SequentialRandomJoinTests(TestCase):
    def setUp(self):
        self.u1, self.u2, self.room = _users_and_room(random_call_room=True)
        self.event = LivekitWebhookEvent.objects.create(data={})

    def test_both_random_joins_share_one_session_and_mark_it_mutual(self):
        process_webhook_random_call__participant_joined(
            {}, self.event, str(self.u1.uuid), self.u1, str(self.room.uuid), self.room
        )
        process_webhook_random_call__participant_joined(
            {}, LivekitWebhookEvent.objects.create(data={}), str(self.u2.uuid), self.u2, str(self.room.uuid), self.room
        )

        sessions = list(LivekitSession.objects.filter(room=self.room))
        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertTrue(session.random_call_session)
        self.assertTrue(session.both_have_been_active)
        self.assertTrue(session.u1_was_active)
        self.assertTrue(session.u2_was_active)
