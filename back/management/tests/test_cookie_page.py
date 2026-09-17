import json

from cookie_consent.models import Cookie, CookieGroup
from django.test import TestCase, override_settings


@override_settings(COOKIE_CONSENT_DOMAIN=None)
class CookieSettingsPageTests(TestCase):
    def setUp(self):
        self.analytics = CookieGroup.objects.create(
            varname="analytics",
            name="analytics_cookiegroup",
            description="Google analytics and Facebook Pixel",
            is_required=False,
            is_deletable=True,
        )
        self.functional = CookieGroup.objects.create(
            varname="lw_func_cookies",
            name="FunctionalityCookies",
            description="Cookies required for basic functionality of Little World",
            is_required=True,
            is_deletable=False,
        )
        Cookie.objects.create(
            cookiegroup=self.analytics,
            name="google_analytics_cookie",
            description="Google analytics cookies and scripts",
            domain="little-world.com",
            path="/",
        )

    def _preferences(self):
        return {"preferences": {"analytics": True}}

    def test_cookies_page_serves_main_frontend_with_hidden_banner(self):
        response = self.client.get("/cookies")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("renderApp", content)
        self.assertIn("/api/cookies/cookie_banner.js?hidden=true", content)
        self.assertNotIn("<h1>Cookies</h1>", content)

    def test_cookies_trailing_slash_redirects_to_spa(self):
        response = self.client.get("/cookies/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/cookies")

    def test_get_cookie_settings_lists_groups_and_cookies(self):
        response = self.client.get("/api/cookies/")

        self.assertEqual(response.status_code, 200)
        groups = {group["varname"]: group for group in response.json()["groups"]}
        self.assertEqual(set(groups), {"analytics", "lw_func_cookies"})

        analytics = groups["analytics"]
        self.assertFalse(analytics["is_required"])
        self.assertEqual(analytics["state"], "unset")
        self.assertEqual(analytics["cookies"][0]["name"], "google_analytics_cookie")

        functional = groups["lw_func_cookies"]
        self.assertTrue(functional["is_required"])
        self.assertEqual(functional["state"], "accepted")

    def test_post_accepts_optional_group_and_sets_consent_cookie(self):
        response = self.client.post(
            "/api/cookies/",
            data=json.dumps(self._preferences()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        groups = {group["varname"]: group for group in response.json()["groups"]}
        self.assertEqual(groups["analytics"]["state"], "accepted")
        self.assertIn("backend_cookie_consent", response.cookies)

        follow_up = self.client.get("/api/cookies/")
        states = {group["varname"]: group["state"] for group in follow_up.json()["groups"]}
        self.assertEqual(states["analytics"], "accepted")

    def test_post_declines_optional_group(self):
        response = self.client.post(
            "/api/cookies/",
            data=json.dumps({"preferences": {"analytics": False}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        groups = {group["varname"]: group for group in response.json()["groups"]}
        self.assertEqual(groups["analytics"]["state"], "declined")
        self.assertIn("backend_cookie_consent", response.cookies)

    def test_required_group_cannot_be_declined(self):
        response = self.client.post(
            "/api/cookies/",
            data=json.dumps({"preferences": {"lw_func_cookies": False}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        groups = {group["varname"]: group for group in response.json()["groups"]}
        self.assertEqual(groups["lw_func_cookies"]["state"], "accepted")
        self.assertNotIn("backend_cookie_consent", response.cookies)

    def test_post_multiple_groups_keeps_all_decisions(self):
        second = CookieGroup.objects.create(
            varname="marketing",
            name="MarketingCookies",
            description="Marketing cookies",
            is_required=False,
            is_deletable=True,
        )
        Cookie.objects.create(cookiegroup=second, name="pixel", description="Pixel")

        response = self.client.post(
            "/api/cookies/",
            data=json.dumps({"preferences": {"analytics": True, "marketing": False}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        groups = {group["varname"]: group for group in response.json()["groups"]}
        self.assertEqual(groups["analytics"]["state"], "accepted")
        self.assertEqual(groups["marketing"]["state"], "declined")

        follow_up = self.client.get("/api/cookies/")
        states = {group["varname"]: group["state"] for group in follow_up.json()["groups"]}
        self.assertEqual(states["analytics"], "accepted")
        self.assertEqual(states["marketing"], "declined")

    def test_legacy_accept_endpoint_still_works(self):
        response = self.client.post("/cookies/accept/analytics/")

        self.assertIn(response.status_code, (200, 302))
        self.assertIn("backend_cookie_consent", response.cookies)
