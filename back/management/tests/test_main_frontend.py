import json
import re

from django.test import TestCase

from management.tests.helpers import register_user


class MainFrontendTemplateTests(TestCase):
    def _extract_cookie_banner_script_url(self, html: str) -> str:
        match = re.search(r"src='([^']*/api/cookies/cookie_banner\.js(?:\?hidden=true)?)'", html)
        self.assertIsNotNone(match, "cookie banner script URL not found in page HTML")
        return match.group(1)

    def _decoded_script_content(self, raw_content: bytes) -> str:
        # The rendered JS escapes quotes as unicode (e.g. \u0022), so decode escapes before assertions.
        return raw_content.decode().encode("utf-8").decode("unicode_escape")

    def _extract_hidden_cookie_banner_value(self, script_content: str) -> bool:
        payload_match = re.search(
            r"const cookieData = JSON\.parse\('(?P<payload>\{.*?\})'\);",
            script_content,
        )
        self.assertIsNotNone(payload_match, "cookie banner payload not found in script")

        cookie_data = json.loads(payload_match.group("payload"))
        return cookie_data["hiddenCookieBanner"]

    def test_public_login_page_loads_non_hidden_cookie_banner(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        self.assertIn("/api/cookies/cookie_banner.js", content)
        self.assertNotIn("/api/cookies/cookie_banner.js?hidden=true", content)

        script_url = self._extract_cookie_banner_script_url(content)
        script_response = self.client.get(script_url)
        self.assertEqual(script_response.status_code, 200)
        script_content = self._decoded_script_content(script_response.content)
        self.assertNotIn("JSON.parse(JSON.parse(", script_content)
        self.assertNotIn("?.hiddenCookieBanner", script_content)
        self.assertFalse(self._extract_hidden_cookie_banner_value(script_content))

    def test_authenticated_app_page_loads_hidden_cookie_banner(self):
        user = register_user()
        user.state.email_authenticated = True
        user.state.set_user_form_completed()
        user.state.save()

        self.client.force_login(user)
        response = self.client.get("/app/")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        self.assertIn("/api/cookies/cookie_banner.js?hidden=true", content)

        script_url = self._extract_cookie_banner_script_url(content)
        script_response = self.client.get(script_url)
        self.assertEqual(script_response.status_code, 200)
        script_content = self._decoded_script_content(script_response.content)
        self.assertNotIn("JSON.parse(JSON.parse(", script_content)
        self.assertNotIn("?.hiddenCookieBanner", script_content)
        self.assertTrue(self._extract_hidden_cookie_banner_value(script_content))
