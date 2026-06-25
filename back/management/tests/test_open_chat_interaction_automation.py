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
from management.models.support_task import SupportTask, SupportTaskAction
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
        matching_user_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.MATCHING_USER.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.MATCHING_USER.codename},
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
        automation_email = (getattr(settings, "OPEN_CHAT_AUTOMATION_USER_EMAIL", "") or "").strip()
        if automation_email and automation_email != cls.admin_user.email:
            cls.automation_user = User.objects.create_user(
                email=automation_email,
                username=automation_email,
                password="Test123!",
                first_name="Automation",
                last_name="User",
            )
        else:
            cls.automation_user = cls.admin_user

        cls.source_user = User.objects.create_user(
            email="open-chat-source@test.de",
            username="open-chat-source@test.de",
            password="Test123!",
            first_name="Source",
            last_name="User",
        )
        cls.matching_source_user = User.objects.create_user(
            email="open-chat-matching-source@test.de",
            username="open-chat-matching-source@test.de",
            password="Test123!",
            first_name="Matching",
            last_name="Source",
        )
        cls.matching_source_user.user_permissions.add(matching_user_permission)

        cls.chat = Chat.objects.create(u1=cls.admin_user, u2=cls.source_user, is_temporary=False)
        cls.source_message = ChatMessage.objects.create(
            chat=cls.chat,
            sender=cls.source_user,
            recipient=cls.admin_user,
            text="Please help me",
            read=False,
        )
        cls.matching_source_chat = Chat.objects.create(
            u1=cls.admin_user, u2=cls.matching_source_user, is_temporary=False
        )
        cls.matching_source_message = ChatMessage.objects.create(
            chat=cls.matching_source_chat,
            sender=cls.matching_source_user,
            recipient=cls.admin_user,
            text="Please help me from matching user",
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
        action = actions.first()
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(
            action.static_parameters.get("chat_uuid"),
            str(self.source_message.chat.uuid),
        )
        self.assertEqual(
            action.static_parameters.get("message_uuid"),
            str(self.source_message.uuid),
        )
        assigned_to = action.task.assigned_to
        created_by = action.task.created_by
        self.assertIsNotNone(assigned_to)
        self.assertIsNotNone(created_by)
        assert assigned_to is not None
        assert created_by is not None
        self.assertEqual(assigned_to.pk, self.admin_user.pk)
        self.assertEqual(created_by.pk, self.automation_user.pk)
        mock_send_task.assert_called_once()
        _, send_task_kwargs = mock_send_task.call_args
        queued_kwargs = send_task_kwargs["kwargs"]
        self.assertEqual(queued_kwargs["support_task_id"], action.task.pk)
        self.assertEqual(queued_kwargs["tool_mode"], "message_reply_suggestion")
        self.assertFalse(queued_kwargs["publish_chat_interaction_message"])

    @patch("management.open_chat_interaction_task.current_app.send_task")
    def test_idempotent_generate_message_replies_skips_matching_user_senders(self, mock_send_task):
        mock_send_task.return_value = MagicMock(id="interaction-task-id")

        result = idempotent_actions__generate_message_replies(
            target_user_uuid=str(self.admin_user.uuid),
            triggered_by_user_uuid=str(self.admin_user.uuid),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["created_tasks_count"], 1)
        self.assertEqual(result["enqueued_interactions_count"], 1)

        matching_user_actions = SupportTaskAction.objects.filter(
            action_type="support_reply",
            static_parameters__message_uuid=str(self.matching_source_message.uuid),
        )
        self.assertEqual(matching_user_actions.count(), 0)
        self.assertIn(
            {
                "source_user_uuid": str(self.matching_source_user.uuid),
                "status": "skipped_matching_user_permission",
            },
            result["processed_messages"],
        )

    @patch("chat.consumers.messages.NewMessage.send")
    @patch("management.open_chat_interaction_task.OpenChatPythonClient")
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

    @patch("chat.consumers.messages.NewMessage.send")
    @patch("management.open_chat_interaction_task.OpenChatPythonClient")
    def test_open_chat_trigger_interaction_plain_mode_stores_interaction_on_support_task(
        self, mock_client_cls, _mock_new_message_send
    ):
        support_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": self.source_message.text[:500],
                "message_uuid": str(self.source_message.uuid),
                "chat_uuid": str(self.chat.uuid),
                "sender_user_id": self.source_user.pk,
                "recipient_user_id": self.admin_user.pk,
            },
            parameters={"message": ""},
            created_by=self.automation_user,
            assigned_to=self.admin_user,
            related_user=self.source_user,
        )

        mock_client = MagicMock()
        mock_client.login.return_value = {"name": "Admin Open Chat"}
        mock_client.create_interaction.return_value = {"uuid": "plain-interaction-uuid"}
        mock_client.get_interactions.return_value = {
            "rows": [{"uuid": "plain-interaction-uuid"}],
            "total_pages": 1,
        }
        mock_client.get_shared_interaction_url.return_value = "http://localhost:1984/interaction/plain-interaction-uuid"
        mock_client_cls.return_value = mock_client

        result = open_chat_trigger_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
            support_task_id=support_task.pk,
            tool_mode="no_tools",
            publish_chat_interaction_message=False,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["interaction_uuid"], "plain-interaction-uuid")
        self.assertIsNone(result["interaction_message_uuid"])
        self.assertFalse(result["tool_called"])
        mock_client.list_interaction_messages.assert_not_called()

        support_action = SupportTaskAction.objects.get(task=support_task)
        self.assertEqual(support_action.static_parameters.get("interaction_id"), "plain-interaction-uuid")

    @patch("chat.consumers.messages.NewMessage.send")
    @patch("management.open_chat_interaction_task.OpenChatPythonClient")
    def test_open_chat_trigger_interaction_uses_message_reply_suggestion_tool(
        self, mock_client_cls, _mock_new_message_send
    ):
        configuration = OpenChatConfiguration.objects.get(user=self.admin_user)
        configuration.interaction_overwrite = {
            "tools": [],
            "system_prompt": "You are a support assistant. Respond naturally without using any external reply tools.",
        }
        configuration.save(update_fields=["interaction_overwrite"])

        support_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": self.source_message.text[:500],
                "message_uuid": str(self.source_message.uuid),
                "chat_uuid": str(self.chat.uuid),
                "sender_user_id": self.source_user.pk,
                "recipient_user_id": self.admin_user.pk,
            },
            parameters={"message": ""},
            created_by=self.automation_user,
            assigned_to=self.admin_user,
            related_user=self.source_user,
        )

        mock_client = MagicMock()
        mock_client.login.return_value = {"name": "Admin Open Chat"}
        mock_client.create_interaction.return_value = {"uuid": "suggestion-interaction-uuid"}
        mock_client.get_interactions.return_value = {
            "rows": [{"uuid": "suggestion-interaction-uuid"}],
            "total_pages": 1,
        }
        mock_client.get_shared_interaction_url.return_value = (
            "http://localhost:1984/interaction/suggestion-interaction-uuid"
        )
        mock_client.list_interaction_messages.return_value = {
            "rows": [{"tool_calls": [{"name": "little_world__generate_message_reply_suggestion"}]}]
        }
        mock_client_cls.return_value = mock_client

        result = open_chat_trigger_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
            support_task_id=support_task.pk,
            tool_mode="message_reply_suggestion",
            publish_chat_interaction_message=False,
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["tool_called"])
        setup_args = mock_client.setup_bot_config.call_args[0][0]
        self.assertEqual(setup_args["tools"], ["little_world__generate_message_reply_suggestion"])
        self.assertIn("little_world__generate_message_reply_suggestion", setup_args["system_prompt"])
        _, create_kwargs = mock_client.create_interaction.call_args
        self.assertIn("tool_init", create_kwargs)
        self.assertIn("message", create_kwargs)
        self.assertEqual(create_kwargs["message"], self.source_message.text)
        tool_init = create_kwargs["tool_init"]
        self.assertIn("little_world__generate_message_reply_suggestion", tool_init)
        suggestion_tool_init = tool_init["little_world__generate_message_reply_suggestion"]
        self.assertEqual(suggestion_tool_init["task_pk"], str(support_task.pk))
        self.assertEqual(suggestion_tool_init["action_id"], str(support_task.action.pk))
        self.assertNotIn("action_id", create_kwargs["message"])

    def test_open_chat_trigger_interaction_skips_message_reply_suggestion_when_action_not_open(self):
        support_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": self.source_message.text[:500],
                "message_uuid": str(self.source_message.uuid),
                "chat_uuid": str(self.chat.uuid),
                "sender_user_id": self.source_user.pk,
                "recipient_user_id": self.admin_user.pk,
            },
            parameters={"message": ""},
            created_by=self.automation_user,
            assigned_to=self.admin_user,
            related_user=self.source_user,
        )
        support_task.action.resolve(SupportTaskAction.Status.CANCELLED, self.admin_user)

        result = open_chat_trigger_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
            support_task_id=support_task.pk,
            tool_mode="message_reply_suggestion",
            publish_chat_interaction_message=False,
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "support_task_action_not_open")

    def test_open_chat_trigger_interaction_skips_message_reply_suggestion_without_support_task_id(self):
        result = open_chat_trigger_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
            tool_mode="message_reply_suggestion",
            publish_chat_interaction_message=False,
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "support_task_action_missing_for_message_reply_suggestion")

    @patch("management.open_chat_interaction_task._create_session_and_csrf_for_user")
    @patch("chat.consumers.messages.NewMessage.send")
    @patch("management.open_chat_interaction_task.OpenChatPythonClient")
    def test_message_reply_suggestion_tool_init_uses_open_chat_task_creator_session(
        self, mock_client_cls, _mock_new_message_send, mock_create_session
    ):
        mock_create_session.return_value = ("session-from-open-chat-user", "csrf-from-open-chat-user")
        support_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": self.source_message.text[:500],
                "message_uuid": str(self.source_message.uuid),
                "chat_uuid": str(self.chat.uuid),
                "sender_user_id": self.source_user.pk,
                "recipient_user_id": self.admin_user.pk,
            },
            parameters={"message": ""},
            created_by=self.automation_user,
            assigned_to=self.admin_user,
            related_user=self.source_user,
        )
        mock_client = MagicMock()
        mock_client.login.return_value = {"name": "Admin Open Chat"}
        mock_client.create_interaction.return_value = {"uuid": "recipient-session-interaction"}
        mock_client.get_interactions.return_value = {
            "rows": [{"uuid": "recipient-session-interaction"}],
            "total_pages": 1,
        }
        mock_client.get_shared_interaction_url.return_value = (
            "http://localhost:1984/interaction/recipient-session-interaction"
        )
        mock_client.list_interaction_messages.return_value = {
            "rows": [{"tool_calls": [{"name": "little_world__generate_message_reply_suggestion"}]}]
        }
        mock_client_cls.return_value = mock_client

        result = open_chat_trigger_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
            support_task_id=support_task.pk,
            tool_mode="message_reply_suggestion",
            publish_chat_interaction_message=False,
        )

        self.assertEqual(result["status"], "ok")
        mock_create_session.assert_called_once_with(support_task.created_by)
