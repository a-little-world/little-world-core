from cookie_consent.models import Cookie, CookieGroup
from django.test import TestCase, override_settings


@override_settings(COOKIE_CONSENT_DOMAIN=None)
class CookieBannerTests(TestCase):
    def setUp(self):
        self.analytics = CookieGroup.objects.create(
            varname="analytics",
            name="analytics_cookiegroup",
            description="Google and Facebook analytics",
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

    def test_cookie_banner_script_still_exposes_group_data(self):
        response = self.client.get("/api/cookies/cookie_banner.js")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("cookieBanner", content)
        self.assertIn("analytics", content)

    def test_legacy_cookies_page_disabled(self):
        for path in ("/cookies", "/cookies/"):
            response = self.client.get(path)

            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "/")

    def test_legacy_accept_endpoint_still_works(self):
        response = self.client.post("/cookies/accept/analytics/")

        self.assertIn(response.status_code, (200, 302))
        self.assertIn("backend_cookie_consent", response.cookies)

    def test_legacy_decline_endpoint_still_works(self):
        response = self.client.post("/cookies/decline/analytics/")

        self.assertIn(response.status_code, (200, 302))
        self.assertIn("backend_cookie_consent", response.cookies)
