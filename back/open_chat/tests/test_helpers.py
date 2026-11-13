from types import SimpleNamespace
from unittest.mock import patch

from chat.models import Chat
from chat.models import Message as ChatMessage
from django.test import SimpleTestCase, TestCase
from management.models.user import User

from open_chat.helpers import (
    build_chat_transcript,
    build_open_chat_client,
    resolve_open_chat_frontend_host,
    rewrite_open_chat_url_for_browser,
)


class BuildOpenChatClientTests(SimpleTestCase):
    def test_uses_password_auth_for_non_token_api_key(self):
        configuration = SimpleNamespace(
            open_chat_host="http://open-chat-go-backend:1984",
            open_chat_user="user@example.com",
            open_chat_api_key="Test123!",
        )

        with (
            patch("open_chat.helpers.OpenChatClient") as client_cls,
            patch("open_chat.helpers.PasswordAuth") as password_auth,
            patch("open_chat.helpers.TokenAuth") as token_auth,
        ):
            client = build_open_chat_client(configuration)

        token_auth.assert_not_called()
        password_auth.assert_called_once_with(email="user@example.com", password="Test123!")
        client_cls.assert_called_once()
        self.assertEqual(client._cookie_domain(), "")

    def test_uses_token_auth_for_prefixed_access_token(self):
        configuration = SimpleNamespace(
            open_chat_host="http://open-chat-go-backend:1984",
            open_chat_user="user@example.com",
            open_chat_api_key="ocat_parent-token",
        )

        with (
            patch("open_chat.helpers.OpenChatClient") as client_cls,
            patch("open_chat.helpers.PasswordAuth") as password_auth,
            patch("open_chat.helpers.TokenAuth") as token_auth,
        ):
            build_open_chat_client(configuration)

        password_auth.assert_not_called()
        token_auth.assert_called_once_with(token="ocat_parent-token")
        client_cls.assert_called_once()

    def test_uses_token_auth_for_uuid_api_key(self):
        token = "81e80af5-2d54-48fb-a7db-71a5a763104c"
        configuration = SimpleNamespace(
            open_chat_host="http://open-chat.example.com:1984",
            open_chat_user="user@example.com",
            open_chat_api_key=token,
        )

        with (
            patch("open_chat.helpers.OpenChatClient") as client_cls,
            patch("open_chat.helpers.PasswordAuth") as password_auth,
            patch("open_chat.helpers.TokenAuth") as token_auth,
        ):
            client = build_open_chat_client(configuration)

        password_auth.assert_not_called()
        token_auth.assert_called_once_with(token=token)
        client_cls.assert_called_once()
        self.assertEqual(client._cookie_domain(), "")


class ResolveOpenChatFrontendHostTests(SimpleTestCase):
    def test_falls_back_to_configuration_host(self):
        configuration = SimpleNamespace(open_chat_host="http://open-chat-go-backend:1984")
        with self.settings(DEFAULT_OPEN_CHAT_FRONTEND_HOST=None):
            self.assertEqual(
                resolve_open_chat_frontend_host(configuration),
                "http://open-chat-go-backend:1984",
            )

    def test_prefers_frontend_host_override(self):
        configuration = SimpleNamespace(open_chat_host="http://open-chat-go-backend:1984")
        with self.settings(DEFAULT_OPEN_CHAT_FRONTEND_HOST="http://localhost:1984"):
            self.assertEqual(
                resolve_open_chat_frontend_host(configuration),
                "http://localhost:1984",
            )

    def test_rewrites_shared_url_origin_for_browser(self):
        configuration = SimpleNamespace(open_chat_host="http://open-chat-go-backend:1984")
        with self.settings(DEFAULT_OPEN_CHAT_FRONTEND_HOST="http://localhost:1984"):
            rewritten = rewrite_open_chat_url_for_browser(
                "http://open-chat-go-backend:1984/interaction/abc",
                configuration,
            )
        self.assertEqual(rewritten, "http://localhost:1984/interaction/abc")


class BuildChatTranscriptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.support_user = User.objects.create_user(
            email="transcript-support@test.de",
            username="transcript-support@test.de",
            password="Test123!",
            first_name="Support",
            last_name="Team",
        )
        cls.other_user = User.objects.create_user(
            email="transcript-user@test.de",
            username="transcript-user@test.de",
            password="Test123!",
            first_name="Other",
            last_name="User",
        )
        cls.chat = Chat.objects.create(u1=cls.support_user, u2=cls.other_user, is_temporary=False)

    def _add_message(self, *, sender, text, parsable=False):
        return ChatMessage.objects.create(
            chat=self.chat,
            sender=sender,
            recipient=self.other_user if sender == self.support_user else self.support_user,
            text=text,
            parsable_message=parsable,
        )

    def test_orders_oldest_first_and_labels_roles(self):
        self._add_message(sender=self.other_user, text="first user message")
        self._add_message(sender=self.support_user, text="support reply")
        self._add_message(sender=self.other_user, text="latest user message")

        transcript = build_chat_transcript(self.chat.uuid, support_user_id=self.support_user.pk)

        self.assertLess(transcript.index("first user message"), transcript.index("support reply"))
        self.assertLess(transcript.index("support reply"), transcript.index("latest user message"))
        self.assertIn("User: first user message", transcript)
        self.assertIn("Support: support reply", transcript)

    def test_excludes_parsable_messages(self):
        self._add_message(sender=self.other_user, text="real message")
        self._add_message(sender=self.other_user, text='{"type": "interaction"}', parsable=True)

        transcript = build_chat_transcript(self.chat.uuid, support_user_id=self.support_user.pk)

        self.assertIn("real message", transcript)
        self.assertNotIn("interaction", transcript)

    def test_returns_empty_when_no_non_parsable_messages(self):
        self._add_message(sender=self.other_user, text="payload", parsable=True)

        self.assertEqual(build_chat_transcript(self.chat.uuid, support_user_id=self.support_user.pk), "")

    def test_truncates_each_message(self):
        self._add_message(sender=self.other_user, text="x" * 500)

        transcript = build_chat_transcript(
            self.chat.uuid,
            support_user_id=self.support_user.pk,
            max_message_chars=50,
        )

        self.assertIn("…", transcript)
        self.assertNotIn("x" * 51, transcript)

    def test_keeps_most_recent_characters_when_truncated(self):
        self._add_message(sender=self.other_user, text="old-message-marker")
        self._add_message(sender=self.other_user, text="new-message-marker")

        transcript = build_chat_transcript(
            self.chat.uuid,
            support_user_id=self.support_user.pk,
            max_chars=30,
        )

        self.assertIn("earlier messages truncated", transcript)
        self.assertIn("new-message-marker", transcript)
        self.assertNotIn("old-message-marker", transcript)
