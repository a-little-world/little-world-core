from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from chat.models import Chat
from chat.models import Message as ChatMessage
from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from management.api.user_advanced_filter import (
    get_user_with_message_to_admin,
    get_user_with_message_to_admin_that_are_read_but_not_replied,
    get_user_with_message_to_admin_that_are_read_or_not_read_but_not_replied,
)
from management.models.support_task import SupportTask, SupportTaskAction
from management.models.user import User
from management.permissions import ManagementPermission

from open_chat.basic_chat_interaction import (
    BASIC_CHAT_INTERACTION_CONTEXT,
    build_basic_chat_interaction_system_prompt,
    open_chat_basic_chat_interaction,
)
from open_chat.helpers import build_chat_transcript, rewrite_open_chat_url_for_browser
from open_chat.interaction_config import (
    DEFAULT_OPEN_CHAT_MAX_TOKENS,
    DEFAULT_OPEN_CHAT_SUGGESTION_MAX_TOKENS,
)
from open_chat.message_reply_suggestion import (
    MESSAGE_REPLY_SUGGESTION_CONTEXT,
    build_message_reply_suggestion_system_prompt,
    idempotent_actions__generate_message_replies,
    open_chat_run_message_reply_suggestion_interaction,
)
from open_chat.models import DEFAULT_OPEN_CHAT_HOST, OpenChatConfiguration
from open_chat.tool_definitions import (
    CHAT_REPLY_REST_TOOL_NAME,
    MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
    RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
    RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
)
from open_chat.tool_definitions_management import (
    MANAGEMENT_REST_TOOL_NAMES,
    build_management_tool_init,
)


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
        reply_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES.codename},
        )

        cls.admin_user = User.objects.create_user(
            email=settings.MATCHING_USER_MAIL,
            username=settings.MATCHING_USER_MAIL,
            password="Test123!",
            first_name="Admin",
            last_name="User",
        )
        cls.admin_user.user_permissions.add(open_chat_permission, reply_permission)
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
        # Automation is granted MATCHING_USER in production so it can use the panel;
        # support-reply creation must still skip its messages.
        cls.automation_user.user_permissions.add(matching_user_permission)

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

    @patch("open_chat.message_reply_suggestion.current_app.send_task")
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
        # Draft is still empty after the first run, so the duplicate task is reused
        # and the interaction is enqueued again.
        self.assertEqual(second_result["enqueued_interactions_count"], 1)
        source_step = next(
            step
            for step in second_result["processed_messages"]
            if step.get("message_uuid") == str(self.source_message.uuid)
        )
        self.assertEqual(source_step["status"], "reused_and_enqueued")

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
        created_by = action.task.created_by
        self.assertIsNotNone(created_by)
        assert created_by is not None
        self.assertFalse(action.task.assignees.exists())
        self.assertEqual(created_by.pk, self.automation_user.pk)
        self.assertEqual(mock_send_task.call_count, 2)
        send_task_args, send_task_kwargs = mock_send_task.call_args
        self.assertEqual(
            send_task_args[0],
            "management.tasks.open_chat_run_message_reply_suggestion_interaction",
        )
        queued_kwargs = send_task_kwargs["kwargs"]
        self.assertEqual(queued_kwargs["support_task_id"], action.task.pk)

    @patch("open_chat.message_reply_suggestion.current_app.send_task")
    def test_idempotent_generate_message_replies_skips_reenqueue_when_draft_exists(self, mock_send_task):
        mock_send_task.return_value = MagicMock(id="interaction-task-id")

        first_result = idempotent_actions__generate_message_replies(
            target_user_uuid=str(self.admin_user.uuid),
            triggered_by_user_uuid=str(self.admin_user.uuid),
        )
        action = SupportTaskAction.objects.get(
            action_type="support_reply",
            static_parameters__message_uuid=str(self.source_message.uuid),
        )
        action.parameters = {"message": "Already generated draft"}
        action.save(update_fields=["parameters"])

        second_result = idempotent_actions__generate_message_replies(
            target_user_uuid=str(self.admin_user.uuid),
            triggered_by_user_uuid=str(self.admin_user.uuid),
        )

        self.assertEqual(first_result["created_tasks_count"], 1)
        self.assertEqual(second_result["created_tasks_count"], 0)
        self.assertEqual(second_result["enqueued_interactions_count"], 0)
        source_step = next(
            step
            for step in second_result["processed_messages"]
            if step.get("message_uuid") == str(self.source_message.uuid)
        )
        self.assertEqual(source_step["status"], "skipped_duplicate")
        mock_send_task.assert_called_once()

    @patch("open_chat.message_reply_suggestion.current_app.send_task")
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

    @patch("open_chat.message_reply_suggestion.current_app.send_task")
    def test_create_support_reply_skips_open_chat_automation_sender(self, mock_send_task):
        from open_chat.message_reply_suggestion import (
            create_or_reuse_support_reply_task_for_message,
        )

        mock_send_task.return_value = MagicMock(id="interaction-task-id")
        if self.automation_user.pk == self.admin_user.pk:
            self.skipTest("Automation user is the same as admin in this settings fixture")

        chat = Chat.objects.create(u1=self.admin_user, u2=self.automation_user, is_temporary=False)
        message = ChatMessage.objects.create(
            chat=chat,
            sender=self.automation_user,
            recipient=self.admin_user,
            text="Automation hello",
            read=False,
        )

        result = create_or_reuse_support_reply_task_for_message(
            latest_message=message,
            source_user=self.automation_user,
            target_user=self.admin_user,
            created_by_user=self.automation_user,
            configuration_user_uuid=str(self.admin_user.uuid),
            enqueue_interaction=True,
        )

        self.assertEqual(result["status"], "skipped_automation_sender")
        self.assertFalse(
            SupportTaskAction.objects.filter(
                action_type="support_reply",
                static_parameters__message_uuid=str(message.uuid),
            ).exists()
        )
        mock_send_task.assert_not_called()

    @patch("open_chat.basic_chat_interaction.ensure_rest_tool_definitions")
    @patch("chat.consumers.messages.NewMessage.send")
    @patch("open_chat.basic_chat_interaction.build_open_chat_client")
    def test_basic_chat_interaction_runs_chat_reply_flow(
        self, mock_client_cls, _mock_new_message_send, mock_ensure_tools
    ):
        mock_client = MagicMock()
        mock_client.login.return_value = SimpleNamespace(name="Admin Open Chat")
        mock_interaction = MagicMock()
        mock_interaction.uuid = "7e4b91f9-2bf9-4f10-b650-11a4345acf71"
        raw_shared_url = "http://localhost:1984/interaction/7e4b91f9-2bf9-4f10-b650-11a4345acf71"
        mock_interaction.shared_url.return_value = raw_shared_url
        mock_client.interact.return_value = mock_interaction
        mock_client_cls.return_value = mock_client
        expected_shared_url = rewrite_open_chat_url_for_browser(
            raw_shared_url,
            SimpleNamespace(open_chat_host=DEFAULT_OPEN_CHAT_HOST),
        )

        result = open_chat_basic_chat_interaction(
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["configuration_owner"], "recipient")
        self.assertEqual(result["session_actor_user_id"], self.source_user.pk)
        self.assertEqual(result["session_actor_email"], self.source_user.email)
        self.assertEqual(result["session_bot_user_id"], self.admin_user.pk)
        self.assertEqual(result["session_bot_email"], self.admin_user.email)
        self.assertEqual(result["interaction_uuid"], "7e4b91f9-2bf9-4f10-b650-11a4345acf71")
        self.assertEqual(result["shared_url"], expected_shared_url)
        mock_interaction.wait_until_finished.assert_not_called()
        mock_ensure_tools.assert_called_once_with(mock_client)
        _, interact_kwargs = mock_client.interact.call_args
        self.assertEqual(interact_kwargs["bot"], "little_world_support_chat")
        self.assertTrue(interact_kwargs["share"])
        overrides = interact_kwargs["overrides"]
        self.assertEqual(overrides["system_prompt"], build_basic_chat_interaction_system_prompt())
        self.assertIn(CHAT_REPLY_REST_TOOL_NAME, overrides["system_prompt"])
        self.assertIn(
            "Use available tools to gather conversation history",
            overrides["system_prompt"],
        )
        self.assertIn("/matching/user/{numeric_id}", overrides["system_prompt"])
        self.assertEqual(overrides["context"], BASIC_CHAT_INTERACTION_CONTEXT)
        self.assertEqual(overrides["max_tokens"], DEFAULT_OPEN_CHAT_MAX_TOKENS)
        self.assertEqual(overrides["temperature"], 0.2)
        self.assertEqual(
            set(overrides["tools"]),
            {
                RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
                RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
                *MANAGEMENT_REST_TOOL_NAMES,
                CHAT_REPLY_REST_TOOL_NAME,
            },
        )
        chat_reply_init = interact_kwargs["tool_init"][CHAT_REPLY_REST_TOOL_NAME]
        past_messages_init = interact_kwargs["tool_init"]["little_world_retrieve_past_messages"]
        permissions_init = interact_kwargs["tool_init"]["little_world_retrieve_management_permissions"]
        self.assertEqual(chat_reply_init["chat_uuid"], str(self.chat.uuid))
        self.assertEqual(past_messages_init["chat_uuid"], str(self.chat.uuid))
        self.assertIn("sessionid=", chat_reply_init["cookie_header"])
        self.assertIn("csrftoken=", chat_reply_init["cookie_header"])
        self.assertTrue(chat_reply_init["api_host"])
        self.assertNotIn("chat_uuid", permissions_init)
        self.assertNotEqual(chat_reply_init["cookie_header"], permissions_init["cookie_header"])
        management_init = build_management_tool_init(
            {
                "api_host": permissions_init["api_host"],
                "cookie_header": permissions_init["cookie_header"],
                "csrf_token": permissions_init["csrf_token"],
            }
        )
        for tool_name in MANAGEMENT_REST_TOOL_NAMES:
            self.assertEqual(interact_kwargs["tool_init"][tool_name], management_init[tool_name])

    @patch("open_chat.message_reply_suggestion.ensure_rest_tool_definitions")
    @patch("chat.consumers.messages.NewMessage.send")
    @patch("open_chat.message_reply_suggestion.build_open_chat_client")
    def test_run_message_reply_suggestion_uses_suggestion_tool(
        self, mock_client_cls, _mock_new_message_send, mock_ensure_tools
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
            related_user=self.source_user,
        )

        mock_client = MagicMock()
        mock_client.login.return_value = SimpleNamespace(name="Admin Open Chat")
        mock_interaction = MagicMock()
        mock_interaction.uuid = "suggestion-interaction-uuid"
        raw_shared_url = "http://localhost:1984/interaction/suggestion-interaction-uuid"
        mock_interaction.shared_url.return_value = raw_shared_url
        mock_client.interact.return_value = mock_interaction
        mock_client_cls.return_value = mock_client
        expected_shared_url = rewrite_open_chat_url_for_browser(
            raw_shared_url,
            SimpleNamespace(open_chat_host=DEFAULT_OPEN_CHAT_HOST),
        )

        older_user_message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.source_user,
            recipient=self.admin_user,
            text="Earlier user question",
        )
        older_support_message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.admin_user,
            recipient=self.source_user,
            text="Earlier support answer",
        )
        parsable_message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.source_user,
            recipient=self.admin_user,
            text='{"type": "interaction"}',
            parsable_message=True,
        )
        earlier = timezone.now() - timedelta(days=1)
        ChatMessage.objects.filter(
            pk__in=[older_user_message.pk, older_support_message.pk, parsable_message.pk]
        ).update(created=earlier)

        expected_transcript = build_chat_transcript(
            str(self.chat.uuid),
            support_user_id=self.admin_user.pk,
        )
        support_context_sentinel = "SENTINEL_SUPPORT_HANDBOOK"

        with patch(
            "open_chat.message_reply_suggestion.build_support_context_prompt_section",
            return_value=support_context_sentinel,
        ):
            result = open_chat_run_message_reply_suggestion_interaction(
                configuration_user_uuid=str(self.admin_user.uuid),
                chat_uuid=str(self.chat.uuid),
                message_uuid=str(self.source_message.uuid),
                sender_uuid=str(self.source_user.uuid),
                recipient_uuid=str(self.admin_user.uuid),
                user_message_text=self.source_message.text,
                support_task_id=support_task.pk,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["shared_url"], expected_shared_url)
        mock_interaction.wait_until_finished.assert_not_called()
        mock_ensure_tools.assert_called_once_with(mock_client)
        _, interact_kwargs = mock_client.interact.call_args
        self.assertEqual(interact_kwargs["bot"], "little_world_reply_suggestion")
        self.assertTrue(interact_kwargs["share"])
        self.assertEqual(interact_kwargs["message"], self.source_message.text)
        overrides = interact_kwargs["overrides"]
        self.assertEqual(
            overrides["system_prompt"],
            build_message_reply_suggestion_system_prompt(
                support_context=support_context_sentinel,
                conversation_context=expected_transcript,
            ),
        )
        self.assertIn(support_context_sentinel, overrides["system_prompt"])
        self.assertIn("Earlier user question", overrides["system_prompt"])
        self.assertIn("Earlier support answer", overrides["system_prompt"])
        self.assertNotIn('{"type": "interaction"}', overrides["system_prompt"])
        self.assertIn(RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME, overrides["system_prompt"])
        self.assertIn(MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME, overrides["system_prompt"])
        self.assertIn("the ONLY way to persist the suggested outcome", overrides["system_prompt"])
        self.assertEqual(overrides["context"], MESSAGE_REPLY_SUGGESTION_CONTEXT)
        self.assertEqual(overrides["max_tokens"], DEFAULT_OPEN_CHAT_SUGGESTION_MAX_TOKENS)
        self.assertEqual(overrides["temperature"], 0.1)
        self.assertEqual(
            overrides["tools"],
            [
                RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
                MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
            ],
        )
        suggestion_init = interact_kwargs["tool_init"]["little_world_message_reply_suggestion"]
        past_messages_init = interact_kwargs["tool_init"]["little_world_retrieve_past_messages"]
        self.assertEqual(suggestion_init["task_pk"], support_task.pk)
        self.assertEqual(past_messages_init["chat_uuid"], str(self.chat.uuid))
        self.assertIn("sessionid=", suggestion_init["cookie_header"])
        self.assertIn("csrftoken=", suggestion_init["cookie_header"])
        self.assertTrue(suggestion_init["api_host"])

        support_action = SupportTaskAction.objects.get(task=support_task)
        self.assertEqual(
            support_action.static_parameters.get("interaction_id"),
            "suggestion-interaction-uuid",
        )
        self.assertEqual(
            support_action.static_parameters.get("shared_interaction_url"),
            expected_shared_url,
        )

    def test_run_message_reply_suggestion_skips_when_action_not_open(self):
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
            related_user=self.source_user,
        )
        support_task.action.resolve(SupportTaskAction.Status.CANCELLED, self.admin_user)

        result = open_chat_run_message_reply_suggestion_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
            support_task_id=support_task.pk,
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "support_task_action_not_open")

    def test_run_message_reply_suggestion_skips_without_support_task_id(self):
        result = open_chat_run_message_reply_suggestion_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "support_task_action_missing")

    @patch("open_chat.helpers._create_session_and_csrf_for_user")
    @patch("chat.consumers.messages.NewMessage.send")
    @patch("open_chat.message_reply_suggestion.build_open_chat_client")
    def test_message_reply_suggestion_tool_init_uses_open_chat_task_creator_session(
        self, mock_client_cls, _mock_new_message_send, mock_create_session
    ):
        mock_create_session.return_value = (
            "session-from-open-chat-user",
            "csrf-from-open-chat-user",
        )
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
            related_user=self.source_user,
        )
        mock_client = MagicMock()
        mock_client.login.return_value = SimpleNamespace(name="Admin Open Chat")
        mock_interaction = MagicMock()
        mock_interaction.uuid = "recipient-session-interaction"
        mock_interaction.shared_url.return_value = "http://localhost:1984/interaction/recipient-session-interaction"
        mock_client.interact.return_value = mock_interaction
        mock_client_cls.return_value = mock_client

        result = open_chat_run_message_reply_suggestion_interaction(
            configuration_user_uuid=str(self.admin_user.uuid),
            chat_uuid=str(self.chat.uuid),
            message_uuid=str(self.source_message.uuid),
            sender_uuid=str(self.source_user.uuid),
            recipient_uuid=str(self.admin_user.uuid),
            user_message_text=self.source_message.text,
            support_task_id=support_task.pk,
        )

        self.assertEqual(result["status"], "ok")
        mock_create_session.assert_called_once_with(support_task.created_by)


class BuildMessageReplySuggestionPromptTests(SimpleTestCase):
    def test_omits_context_sections_when_context_is_empty(self):
        prompt = build_message_reply_suggestion_system_prompt(
            support_context="",
            conversation_context="",
        )

        self.assertNotIn("Support handbook and reply templates", prompt)
        self.assertNotIn("Conversation context", prompt)

    def test_injects_support_and_conversation_context_in_order(self):
        prompt = build_message_reply_suggestion_system_prompt(
            support_context="Support handbook and reply templates (authoritative guidance):\nHALLMARK",
            conversation_context="[2026-01-01 10:00] User: hi",
        )

        self.assertIn("HALLMARK", prompt)
        self.assertIn("Conversation context (oldest → newest):", prompt)
        self.assertIn("[2026-01-01 10:00] User: hi", prompt)
        self.assertLess(prompt.index("HALLMARK"), prompt.index("Your tools:"))
        self.assertLess(prompt.index("Conversation context (oldest"), prompt.index("Reminder:"))

    def test_skills_section_is_omitted_by_default(self):
        prompt = build_message_reply_suggestion_system_prompt(
            support_context="",
            conversation_context="",
            include_skills=False,
        )

        self.assertNotIn("Outcome skills", prompt)

    def test_skills_section_lists_outcomes_and_threads_when_enabled(self):
        prompt = build_message_reply_suggestion_system_prompt(
            support_context="",
            conversation_context="",
            include_skills=True,
            slack_threads=[{"key": "praise", "label": "Praise"}],
        )

        self.assertIn("Outcome skills", prompt)
        self.assertIn("mark_read", prompt)
        self.assertIn("slack_feedback", prompt)
        self.assertIn("keep_open", prompt)
        self.assertIn("Available Slack thread keys: praise", prompt)
