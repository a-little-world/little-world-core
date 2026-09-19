from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from management.api.user import get_user_data
from management.models.matches import Match
from management.models.mobile_device import MobileDevice, MobileDeviceQuerySet
from management.models.state import FrontendStatusEnum, FrontendStatusSerializer, State
from management.models.unconfirmed_matches import MatchType
from management.models.user import PushNotificationType, User


class ChangePasswordTests(TestCase):
    def test_password_change_via_api(self):
        pass  # TODO!


class ChangeEmailTests(TestCase):
    def test_email_change(self):
        pass  # TODO!


class PushDevicesNotificationTypeTests(TestCase):
    """notification_type arrives as a plain str after a round trip through Celery's
    JSON serializer — push_devices must accept that the same as the enum member."""

    def setUp(self):
        self.user = User.objects.create_user(
            email=f"push-devices-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )
        MobileDevice.objects.create(user=self.user, active=True, registration_id=str(uuid4()))

    def test_accepts_enum_member(self):
        self.assertEqual(self.user.push_devices(PushNotificationType.CHAT).count(), 1)

    def test_accepts_plain_string_like_celery_would_deliver(self):
        self.assertEqual(self.user.push_devices("chat").count(), 1)


class SendTestPushNotificationApiTests(TestCase):
    """The push notification APIs must pass a notification_type — it became required
    and the endpoints kept calling without it, which raised a TypeError."""

    def setUp(self):
        self.user = User.objects.create_user(
            email=f"push-api-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)

    def test_send_test_notification(self):
        with patch.object(MobileDeviceQuerySet, "send_message") as send_message:
            response = self.client.post("/api/push_notifications/send_test")

        self.assertEqual(response.status_code, 200)
        send_message.assert_called_once()

    def test_send_notification(self):
        with patch.object(MobileDeviceQuerySet, "send_message") as send_message:
            response = self.client.post(
                "/api/push_notifications/send",
                {"user": self.user.id, "title": "Title", "description": "Description"},
            )

        self.assertEqual(response.status_code, 200)
        send_message.assert_called_once()


class JourneyMatchOnUserPayloadTests(TestCase):
    def _user(self, prefix: str) -> User:
        user = User.objects.create_user(
            email=f"{prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name=prefix,
        )
        user.state.user_form_state = State.UserFormStateChoices.FILLED
        user.state.save(update_fields=["user_form_state"])
        return user

    def test_temporary_lobby_match_does_not_count_as_has_match(self):
        user1 = self._user("tmp-a")
        user2 = self._user("tmp-b")
        user1.state.searching_state = State.SearchingStateChoices.SEARCHING
        user1.state.save(update_fields=["searching_state"])
        Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.TEMPORARY,
            support_matching=False,
            active=False,
            confirmed=True,
        )

        payload = get_user_data(user1)
        self.assertFalse(payload["hasMatch"])
        self.assertEqual(
            FrontendStatusSerializer(user1.state).data["status"],
            FrontendStatusEnum.searching_no_match.value,
        )

    def test_random_call_match_counts_as_has_match(self):
        user1 = self._user("rc-a")
        user2 = self._user("rc-b")
        user1.state.searching_state = State.SearchingStateChoices.SEARCHING
        user1.state.save(update_fields=["searching_state"])
        Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.RANDOM_CALL,
            support_matching=False,
            active=True,
            confirmed=False,
        )

        payload = get_user_data(user1)
        self.assertTrue(payload["hasMatch"])
        self.assertEqual(
            FrontendStatusSerializer(user1.state).data["status"],
            FrontendStatusEnum.matched_searching.value,
        )
