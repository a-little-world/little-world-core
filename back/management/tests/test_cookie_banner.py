from cookie_consent.models import Cookie, CookieGroup
from cookie_consent.util import get_cookie_value_from_request
from django.test import RequestFactory, TestCase, override_settings


@override_settings(COOKIE_CONSENT_DOMAIN=None)
class CookieBannerTests(TestCase):
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

    def test_cookie_banner_script_still_exposes_group_data(self):
        response = self.client.get("/api/cookies/cookie_banner.js")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("cookieBanner", content)
        self.assertIn("analytics", content)

    def test_percent_encoded_consent_cookie_is_decoded(self):
        # The banner also writes the consent cookie from the browser (js-cookie),
        # which percent-encodes the value. It must not break parsing.
        request = RequestFactory().get(
            "/",
            HTTP_COOKIE="backend_cookie_consent=analytics%3D-1%7Clw_func_cookies%3D2026-09-17T19%3A07%3A04.728Z",
        )

        self.assertFalse(get_cookie_value_from_request(request, "analytics"))

    def test_cookie_banner_script_survives_percent_encoded_consent_cookie(self):
        # Regression: an encoded cookie used to raise ValueError and return a 500,
        # so the banner bundle never loaded.
        response = self.client.get(
            "/api/cookies/cookie_banner.js",
            HTTP_COOKIE="backend_cookie_consent=analytics%3D-1%7Clw_func_cookies%3D2026-09-17T19%3A07%3A04.728Z",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")

    def test_legacy_accept_endpoint_still_works(self):
        response = self.client.post("/cookies/accept/analytics/")

        self.assertIn(response.status_code, (200, 302))
        self.assertIn("backend_cookie_consent", response.cookies)

    def test_legacy_decline_endpoint_still_works(self):
        response = self.client.post("/cookies/decline/analytics/")

        self.assertIn(response.status_code, (200, 302))
        self.assertIn("backend_cookie_consent", response.cookies)
