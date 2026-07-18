from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from open_chat.helpers import build_chat_text_markup_hint, build_open_chat_client


class BuildChatTextMarkupHintTests(SimpleTestCase):
    def test_requires_anchor_widget_syntax_for_links(self):
        hint = build_chat_text_markup_hint("http://localhost:8000")

        self.assertIn("Never paste bare URLs", hint)
        self.assertIn("never set page_size below 20", hint)
        self.assertIn("page_size=20", hint)
        self.assertNotIn("page_size=5", hint)
        self.assertIn('<a {"href": "http://localhost:8000/matching/user/22", "target": "_blank"}>', hint)
        self.assertIn("View onboarded learners", hint)
        self.assertNotIn("or bare https:// URLs", hint)


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
