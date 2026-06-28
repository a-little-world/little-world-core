from django.test import SimpleTestCase

from open_chat.helpers import build_chat_text_markup_hint


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
