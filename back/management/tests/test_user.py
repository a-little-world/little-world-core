from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from management.models.mobile_device import MobileDevice, MobileDeviceQuerySet
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

    def test_excludes_when_category_disabled(self):
        self.user.profile.push_notifications_random_calls_enabled = False
        self.user.profile.save()
        self.assertEqual(self.user.push_devices("random_call_reminder").count(), 0)


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
