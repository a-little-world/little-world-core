from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from management.models.support_task import SupportTask, SupportTaskAction
from management.models.user import User
from management.permissions import ManagementPermission


class AdvancedUserMessageReplyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        content_type = ContentType.objects.get(app_label="management", model="state")
        can_send_support_message_replies_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES.codename},
        )

        cls.support_user = User.objects.create_user(
            email="support-user@test.de",
            username="support-user@test.de",
            password="Test123!",
            first_name="Support",
            last_name="User",
        )
        cls.support_user.is_staff = True
        cls.support_user.save(update_fields=["is_staff"])
        cls.support_user.user_permissions.add(can_send_support_message_replies_permission)

        cls.staff_without_permission = User.objects.create_user(
            email="staff-no-reply-perm@test.de",
            username="staff-no-reply-perm@test.de",
            password="Test123!",
            first_name="No",
            last_name="Permission",
        )
        cls.staff_without_permission.is_staff = True
        cls.staff_without_permission.save(update_fields=["is_staff"])

        cls.target_user = User.objects.create_user(
            email="reply-target@test.de",
            username="reply-target@test.de",
            password="Test123!",
            first_name="Reply",
            last_name="Target",
        )

    def _build_open_support_reply_task(self) -> SupportTask:
        return SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": "Initial incoming message",
                "message_uuid": "test-message-uuid",
                "chat_uuid": "test-chat-uuid",
                "sender_user_id": self.target_user.pk,
                "recipient_user_id": self.target_user.pk,
            },
            parameters={"message": ""},
            created_by=self.support_user,
            assigned_to=self.support_user,
            related_user=self.target_user,
        )

    @patch("chat.consumers.messages.NewMessage.send")
    def test_message_reply_updates_and_closes_open_support_reply_task(self, _mock_new_message_send):
        support_task = self._build_open_support_reply_task()
        endpoint = f"/api/matching/users/{self.target_user.pk}/message_reply/"

        client = APIClient()
        client.force_authenticate(user=self.support_user)
        response = client.post(endpoint, {"message": "Final selected support reply"}, format="json")

        self.assertEqual(response.status_code, 200)
        support_action = SupportTaskAction.objects.get(task=support_task)
        support_task.refresh_from_db()

        self.assertEqual(support_action.parameters.get("message"), "Final selected support reply")
        self.assertEqual(support_action.status, SupportTaskAction.Status.EXECUTED)
        self.assertEqual(support_task.status, SupportTask.Status.COMPLETED)

    @patch("chat.consumers.messages.NewMessage.send")
    def test_message_reply_requires_can_send_support_message_replies_permission(self, _mock_new_message_send):
        support_task = self._build_open_support_reply_task()
        endpoint = f"/api/matching/users/{self.target_user.pk}/message_reply/"

        client = APIClient()
        client.force_authenticate(user=self.staff_without_permission)
        response = client.post(endpoint, {"message": "Should be rejected"}, format="json")

        self.assertEqual(response.status_code, 403)
        support_action = SupportTaskAction.objects.get(task=support_task)
        self.assertEqual(support_action.status, SupportTaskAction.Status.OPEN)
        self.assertEqual(support_action.parameters.get("message"), "")
