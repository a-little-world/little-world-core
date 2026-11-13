from unittest.mock import patch

from chat.helpers import MessageSendValidationError, process_message_attachment
from chat.models import Chat, Message
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from management.controller import get_base_management_user
from management.models.matches import Match
from management.models.support_task import SupportTask, SupportTaskAction
from management.models.user import User
from management.permissions import ManagementPermission
from management.support_reply_outcomes import READ_CLOSURE_NOTE


class MessageSendHelperTests(TestCase):
    def test_process_message_attachment_rejects_oversized_file(self):
        oversized_file = SimpleUploadedFile("large.pdf", b"x" * (3 * 1024 * 1024 + 1), content_type="application/pdf")

        with self.assertRaises(MessageSendValidationError):
            process_message_attachment(oversized_file, "caption")


class AdvancedUserMessageReplyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        content_type = ContentType.objects.get(app_label="management", model="state")
        can_send_support_message_replies_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES.codename},
        )
        matching_user_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.MATCHING_USER.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.MATCHING_USER.codename},
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

        cls.reply_manager_with_access = User.objects.create_user(
            email="reply-manager-with-access@test.de",
            username="reply-manager-with-access@test.de",
            password="Test123!",
            first_name="Reply",
            last_name="ManagerWithAccess",
        )
        cls.reply_manager_with_access.user_permissions.add(
            can_send_support_message_replies_permission,
            matching_user_permission,
        )

        cls.reply_manager_without_access = User.objects.create_user(
            email="reply-manager-without-access@test.de",
            username="reply-manager-without-access@test.de",
            password="Test123!",
            first_name="Reply",
            last_name="ManagerWithoutAccess",
        )
        cls.reply_manager_without_access.user_permissions.add(
            can_send_support_message_replies_permission,
            matching_user_permission,
        )

        cls.target_user = User.objects.create_user(
            email="reply-target@test.de",
            username="reply-target@test.de",
            password="Test123!",
            first_name="Reply",
            last_name="Target",
        )
        cls.reply_manager_with_access.grant_management_access(cls.target_user, granted_by=cls.support_user)

        base_management_user = get_base_management_user()
        Match.objects.create(
            user1=base_management_user,
            user2=cls.target_user,
            support_matching=True,
            active=True,
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
            related_user=self.target_user,
        )

    @patch("chat.helpers.send_email_background.delay")
    @patch("chat.consumers.messages.NewMessage.send")
    def test_message_reply_updates_and_closes_open_support_reply_task(self, _mock_new_message_send, _mock_email):
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

    @patch("chat.helpers.send_email_background.delay")
    @patch("chat.consumers.messages.NewMessage.send")
    def test_message_reply_with_attachment(self, _mock_new_message_send, _mock_email):
        support_task = self._build_open_support_reply_task()
        endpoint = f"/api/matching/users/{self.target_user.pk}/message_reply/"
        uploaded_file = SimpleUploadedFile("support-note.pdf", b"pdf-bytes", content_type="application/pdf")

        client = APIClient()
        client.force_authenticate(user=self.support_user)
        response = client.post(
            endpoint,
            {"message": "Please see the attached note", "file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        support_action = SupportTaskAction.objects.get(task=support_task)
        self.assertEqual(support_action.parameters.get("message"), "Please see the attached note")
        self.assertEqual(support_action.status, SupportTaskAction.Status.EXECUTED)

        created_message = Message.objects.order_by("-pk").first()
        self.assertIsNotNone(created_message)
        assert created_message is not None
        self.assertTrue(created_message.parsable_message)
        self.assertIn("AttachmentWidget", created_message.text)
        self.assertIsNotNone(created_message.attachments)

    @patch("chat.helpers.send_email_background.delay")
    @patch("chat.consumers.messages.NewMessage.send")
    def test_message_reply_requires_can_send_support_message_replies_permission(
        self, _mock_new_message_send, _mock_email
    ):
        support_task = self._build_open_support_reply_task()
        endpoint = f"/api/matching/users/{self.target_user.pk}/message_reply/"

        client = APIClient()
        client.force_authenticate(user=self.staff_without_permission)
        response = client.post(endpoint, {"message": "Should be rejected"}, format="json")

        self.assertEqual(response.status_code, 403)
        support_action = SupportTaskAction.objects.get(task=support_task)
        self.assertEqual(support_action.status, SupportTaskAction.Status.OPEN)
        self.assertEqual(support_action.parameters.get("message"), "")

    @patch("chat.helpers.send_email_background.delay")
    @patch("chat.consumers.messages.NewMessage.send")
    def test_message_reply_allows_non_staff_manager_with_permission_and_access(
        self, _mock_new_message_send, _mock_email
    ):
        endpoint = f"/api/matching/users/{self.target_user.pk}/message_reply/"

        client = APIClient()
        client.force_authenticate(user=self.reply_manager_with_access)
        response = client.post(endpoint, {"message": "Allowed manager reply"}, format="json")

        self.assertEqual(response.status_code, 200)

    @patch("chat.helpers.send_email_background.delay")
    @patch("chat.consumers.messages.NewMessage.send")
    def test_message_reply_blocks_non_staff_manager_without_user_access(self, _mock_new_message_send, _mock_email):
        endpoint = f"/api/matching/users/{self.target_user.pk}/message_reply/"

        client = APIClient()
        client.force_authenticate(user=self.reply_manager_without_access)
        response = client.post(endpoint, {"message": "Blocked manager reply"}, format="json")

        self.assertEqual(response.status_code, 404)

    @patch("chat.helpers.send_email_background.delay")
    @patch("chat.consumers.messages.NewMessage.send")
    def test_message_mark_read_closes_support_reply_task_and_logs_note(self, _mock_new_message_send, _mock_email):
        base_management_user = get_base_management_user()
        chat = Chat.objects.create(u1=self.target_user, u2=base_management_user, is_temporary=False)
        message = Message.objects.create(
            chat=chat,
            sender=self.target_user,
            recipient=base_management_user,
            text="Please close this",
            read=False,
        )
        support_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": message.text,
                "message_uuid": str(message.uuid),
                "chat_uuid": str(chat.uuid),
                "sender_user_id": self.target_user.pk,
                "recipient_user_id": base_management_user.pk,
            },
            parameters={"message": ""},
            created_by=self.support_user,
            related_user=self.target_user,
        )

        client = APIClient()
        client.force_authenticate(user=self.support_user)
        response = client.post(
            f"/api/matching/users/{self.target_user.pk}/message_mark_read/",
            {"message_id": str(message.uuid)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["support_task_closed"])
        self.assertEqual(response.data["support_task_id"], support_task.pk)

        message.refresh_from_db()
        support_task.refresh_from_db()
        self.assertTrue(message.read)
        self.assertEqual(support_task.status, SupportTask.Status.COMPLETED)
        self.assertEqual(support_task.action.status, SupportTaskAction.Status.EXECUTED)

        note = support_task.notes.get(text=READ_CLOSURE_NOTE)
        self.assertEqual(note.created_by_id, self.support_user.pk)

    def test_keep_open_keeps_task_open_and_reschedules(self):
        support_task = self._build_open_support_reply_task()

        client = APIClient()
        client.force_authenticate(user=self.support_user)
        response = client.post(
            f"/api/support_task/{support_task.pk}/action/keep_open/",
            {
                "parameters": {
                    "note": "Waiting for the user's documents",
                    "scheduled_at": "2030-01-01T10:00:00Z",
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        support_task.refresh_from_db()
        support_action = SupportTaskAction.objects.get(task=support_task)

        self.assertEqual(support_task.status, SupportTask.Status.IN_PROGRESS)
        self.assertIsNotNone(support_task.scheduled_at)
        self.assertEqual(support_action.status, SupportTaskAction.Status.OPEN)
        self.assertEqual(support_action.parameters.get("suggested_action"), "keep_open")
        note = support_task.notes.get(text="Waiting for the user's documents")
        self.assertEqual(note.created_by_id, self.support_user.pk)

    def test_keep_open_rejects_invalid_scheduled_at(self):
        support_task = self._build_open_support_reply_task()

        client = APIClient()
        client.force_authenticate(user=self.support_user)
        response = client.post(
            f"/api/support_task/{support_task.pk}/action/keep_open/",
            {"parameters": {"scheduled_at": "not-a-date"}},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        support_task.refresh_from_db()
        self.assertEqual(support_task.status, SupportTask.Status.NEW)

    @override_settings(
        USE_SLACK_INTEGRATION=True,
        SLACK_SUPPORT_FEEDBACK_THREADS={"praise": {"channel_id": "C123", "thread_ts": "1.234", "label": "Praise"}},
    )
    @patch("slack_sdk.WebClient.chat_postMessage")
    def test_slack_feedback_execute_posts_to_thread_and_logs_note(self, mock_chat_post_message):
        support_task = self._build_open_support_reply_task()
        support_action = SupportTaskAction.objects.get(task=support_task)
        support_action.parameters = {
            "suggested_action": "slack_feedback",
            "slack_message": "Thank you for the lovely feedback!",
            "slack_thread": "praise",
        }
        support_action.save(update_fields=["parameters"])

        client = APIClient()
        client.force_authenticate(user=self.support_user)
        response = client.post(
            f"/api/support_task/{support_task.pk}/action/execute/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        mock_chat_post_message.assert_called_once()
        _, kwargs = mock_chat_post_message.call_args
        self.assertEqual(kwargs["channel"], "C123")
        self.assertEqual(kwargs["thread_ts"], "1.234")
        self.assertIn("Thank you for the lovely feedback!", kwargs["text"])

        support_task.refresh_from_db()
        support_action.refresh_from_db()
        self.assertEqual(support_action.status, SupportTaskAction.Status.EXECUTED)
        self.assertEqual(support_task.status, SupportTask.Status.COMPLETED)
        note = support_task.notes.get()
        self.assertEqual(note.created_by_id, self.support_user.pk)
        self.assertIn("praise", note.text)
