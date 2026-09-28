from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType
from management.models.user import User

from video.livekit_webhook import _send_after_first_matched_call_message
from video.models import LivekitSession


class FirstMatchedCallMessageTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user(
            email="first-call-one@test.de",
            password="x",
            first_name="Anna",
            last_name="One",
        )
        self.u2 = User.objects.create_user(
            email="first-call-two@test.de",
            password="x",
            first_name="Ben",
            last_name="Two",
        )

    def _match(self, match_type=MatchType.STANDARD):
        return Match.objects.create(
            user1=self.u1,
            user2=self.u2,
            match_type=match_type,
            support_matching=False,
        )

    def _completed_call(self, *, random=False):
        return LivekitSession.objects.create(
            u1=self.u1,
            u2=self.u2,
            both_have_been_active=True,
            random_call_session=random,
            is_active=False,
            end_time=timezone.now(),
        )

    @patch.object(User, "message", autospec=True)
    def test_first_call_after_match_messages_both_users_with_partner_names(self, message):
        self._match()
        session = self._completed_call()

        _send_after_first_matched_call_message(session)

        self.assertEqual(message.call_count, 2)
        by_recipient = {call.args[0].pk: call.args[1] for call in message.call_args_list}
        self.assertIn("Hallo Anna", by_recipient[self.u1.pk])
        self.assertIn("ersten Gespräch mit Ben", by_recipient[self.u1.pk])
        self.assertIn("Hallo Ben", by_recipient[self.u2.pk])
        self.assertIn("ersten Gespräch mit Anna", by_recipient[self.u2.pk])
        self.assertIn("/app/resources/trainings/interkulturelle-kommunikation", by_recipient[self.u1.pk])

    @patch.object(User, "message", autospec=True)
    def test_later_matched_calls_do_not_send_again(self, message):
        self._match()
        self._completed_call()
        later_session = self._completed_call()

        _send_after_first_matched_call_message(later_session)

        message.assert_not_called()

    @patch.object(User, "message", autospec=True)
    def test_random_call_does_not_send_or_block_first_later_matched_call(self, message):
        self._completed_call(random=True)
        self._match(match_type=MatchType.RANDOM_CALL)
        first_matched_session = self._completed_call()

        _send_after_first_matched_call_message(first_matched_session)

        self.assertEqual(message.call_count, 2)

    @patch.object(User, "message", autospec=True)
    def test_temporary_match_does_not_send(self, message):
        self._match(match_type=MatchType.TEMPORARY)
        session = self._completed_call()

        _send_after_first_matched_call_message(session)

        message.assert_not_called()
