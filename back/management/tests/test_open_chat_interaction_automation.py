from unittest.mock import MagicMock, patch

from chat.models import Chat
from chat.models import Message as ChatMessage
from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from management.api.user_advanced_filter import (
    get_user_with_message_to_admin,
    get_user_with_message_to_admin_that_are_read_but_not_replied,
    get_user_with_message_to_admin_that_are_read_or_not_read_but_not_replied,
)
from management.models.open_chat_configuration import DEFAULT_OPEN_CHAT_HOST, OpenChatConfiguration
from management.models.support_task import SupportTaskAction
from management.models.user import User
from management.open_chat_interaction_task import (
    idempotent_actions__generate_message_replies,
    open_chat_trigger_interaction,
)
from management.permissions import ManagementPermission


class UserAdvancedFilterMessageReplyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            email=settings.MATCHING_USER_MAIL,
            username=settings.MATCHING_USER_MAIL,
            password="Test123!",
            first_name="Admin",
            last_name="User",
        )
        cls.user_unread = User.objects.create_user(
            email="user-unread@test.de",
            username="user-unread@test.de",
            password="Test123!",
            first_name="Unread",
            last_name="User",
        )
        cls.user_read = User.objects.create_user(
            email="user-read@test.de",
            username="user-read@test.de",
            password="Test123!",
            first_name="Read",
            last_name="User",
        )
        cls.user_replied = User.objects.create_user(
            email="user-replied@test.de",
            username="user-replied@test.de",
            password="Test123!",
            first_name="Replied",
            last_name="User",
        )

        chat_unread = Chat.objects.create(u1=cls.admin_user, u2=cls.user_unread, is_temporary=False)
        ChatMessage.objects.create(
            chat=chat_unread,
            sender=cls.user_unread,
            recipient=cls.admin_user,
            text="Unread user message",
            read=False,
        )

        chat_read = Chat.objects.create(u1=cls.admin_user, u2=cls.user_read, is_temporary=False)
        ChatMessage.objects.create(
            chat=chat_read,
            sender=cls.user_read,
            recipient=cls.admin_user,
            text="Read user message",
            read=True,
        )

        chat_replied = Chat.objects.create(u1=cls.admin_user, u2=cls.user_replied, is_temporary=False)
        ChatMessage.objects.create(
            chat=chat_replied,
            sender=cls.user_replied,
            recipient=cls.admin_user,
            text="Initial user message",
            read=True,
        )
        ChatMessage.objects.create(
            chat=chat_replied,
            sender=cls.admin_user,
            recipient=cls.user_replied,
            text="Admin reply",
            read=False,
        )

    def test_read_or_unread_not_replied_returns_union_of_pending_users(self):
        unread_ids = set(get_user_with_message_to_admin().values_list("id", flat=True))
        read_ids = set(get_user_with_message_to_admin_that_are_read_but_not_replied().values_list("id", flat=True))
        union_ids = set(
            get_user_with_message_to_admin_that_are_read_or_not_read_but_not_replied().values_list("id", flat=True)
        )

        self.assertEqual(unread_ids, {self.user_unread.id})
        self.assertEqual(read_ids, {self.user_read.id})
        self.assertEqual(union_ids, {self.user_unread.id, self.user_read.id})
        self.assertNotIn(self.user_replied.id, union_ids)


class OpenChatInteractionAutomationTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        content_type = ContentType.objects.get(app_label="management", model="state")
        open_chat_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.OPEN_CHAT_ACCESS.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.OPEN_CHAT_ACCESS.codename},
        )

        cls.admin_user = User.objects.create_user(
            email=settings.MATCHING_USER_MAIL,
            username=settings.MATCHING_USER_MAIL,
            password="Test123!",
            first_name="Admin",
            last_name="User",
        )
        cls.admin_user.user_permissions.add(open_chat_permission)
        OpenChatConfiguration.objects.create(
            user=cls.admin_user,
            open_chat_api_key="admin-key",
            open_chat_user="admin-open-chat-user",
            open_chat_host=DEFAULT_OPEN_CHAT_HOST,
        )

        cls.source_user = User.objects.create_user(
            email="open-chat-source@test.de",
            username="open-chat-source@test.de",
            password="Test123!",
            first_name="Source",
            last_name="User",
        )

        cls.chat = Chat.objects.create(u1=cls.admin_user, u2=cls.source_user, is_temporary=False)
        cls.source_message = ChatMessage.objects.create(
            chat=cls.chat,
            sender=cls.source_user,
            recipient=cls.admin_user,
            text="Please help me",
            read=False,
        )

    @patch("management.open_chat_interaction_task.current_app.send_task")
    def test_idempotent_generate_message_replies_creates_single_task_per_message(self, mock_send_task):
        mock_send_task.return_value = MagicMock(id="interaction-task-id")

        first_result = idempotent_actions__generate_message_replies(
            target_user_uuid=str(self.admin_user.uuid),
            triggered_by_user_uuid=str(self.admin_user.uuid),
        )
        second_result = idempotent_actions__generate_message_replies(
            target_user_uuid=str(self.admin_user.uuid),
            triggered_by_user_uuid=str(self.admin_user.uuid),
        )

        self.assertEqual(first_result["status"], "ok")
        self.assertEqual(first_result["created_tasks_count"], 1)
        self.assertEqual(first_result["enqueued_interactions_count"], 1)
        self.assertEqual(second_result["created_tasks_count"], 0)
        self.assertEqual(second_result["enqueued_interactions_count"], 0)

        actions = SupportTaskAction.objects.filter(
            action_type="support_reply",
            static_parameters__message_uuid=str(self.source_message.uuid),
        )
        self.assertEqual(actions.count(), 1)
        mock_send_task.assert_called_once()

    @patch("chat.consumers.messages.NewMessage.send")
    @patch("client.client.OpenChatPythonClient")
    def test_open_chat_trigger_interaction_uses_explicit_configuration(self, mock_client_cls, _mock_new_message_send):
        mock_client = MagicMock()
        mock_client.login.return_value = {"name": "Admin Open Chat"}
        mock_client.create_interaction.return_value = {"uuid": "7e4b91f9-2bf9-4f10-b650-11a4345acf71"}
        mock_client.get_interactions.return_value = {
            "rows": [{"uuid": "7e4b91f9-2bf9-4f10-b650-11a4345acf71"}],
            "total_pages": 1,
        }
        mock_client.get_shared_interaction_url.return_value = (
            "http://localhost:1984/interaction/7e4b91f9-2bf9-4f10-b650-11a4345acf71"
        )
        mock_client.list_interaction_messages.return_value = {
            "rows": [{"tool_calls": [{"name": "little_world__chat_reply"}]}]
        }
        mock_client_cls.return_value = mock_client

        result = open_chat_trigger_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["configuration_owner"], "explicit_configuration_user")
        self.assertEqual(result["interaction_uuid"], "7e4b91f9-2bf9-4f10-b650-11a4345acf71")
