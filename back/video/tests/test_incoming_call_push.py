from unittest.mock import patch

from chat.models import ChatConnections
from django.test import TestCase
from management.models.user import User
from video.livekit_webhook import process_webhook_classic_call__participant_joined
from video.models import LiveKitRoom, LivekitWebhookEvent


class IncomingCallPushTests(TestCase):
    def setUp(self):
        self.caller = User.objects.create_user(email="caller@test.de", password="x", first_name="Cal", last_name="Ler")
        self.callee = User.objects.create_user(email="callee@test.de", password="x", first_name="Cal", last_name="Lee")
        self.room = LiveKitRoom.objects.create(u1=self.caller, u2=self.callee)
        self.event = LivekitWebhookEvent.objects.create(data={})

    def _join(self, user):
        with (
            patch("video.livekit_webhook.push_notification_background") as push,
            patch("video.livekit_webhook.NewActiveCallRoom"),
        ):
            process_webhook_classic_call__participant_joined(
                {}, self.event, str(user.uuid), user, str(self.room.uuid), self.room
            )
        return push.delay

    def test_push_sent_when_callee_offline(self):
        push = self._join(self.caller)
        push.assert_called_once()
        self.assertEqual(push.call_args.args[0], self.callee.pk)

    def test_no_push_when_callee_online(self):
        ChatConnections.objects.create(user=self.callee, is_online=True)
        self._join(self.caller).assert_not_called()

    def test_no_push_to_caller_when_callee_answers(self):
        self._join(self.caller)
        ChatConnections.objects.create(user=self.callee, is_online=True)
        self._join(self.callee).assert_not_called()
