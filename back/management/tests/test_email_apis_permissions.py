"""
Permission tests for the (now standalone) emails django module.

Even though the email APIs live inside `back/emails/api/` they are tightly
integrated with this project's permission model:

    - All "management" / template / send / dynamic-template endpoints MUST
      be admin-only (django staff OR users carrying the explicit
      `MATCHING_USER` extra-user-permission).  In `back/back/settings.py`
      this is wired up via the `EMAILS_APP.ADMIN_API_PERMISSION_CLASSES`
      setting which points to `management.helpers.IsAdminOrMatchingUser`.

    - The hash-based public unsubscribe endpoints MUST stay accessible to
      anonymous clients (so users can click an unsubscribe link from inside
      an email without being logged in).

These tests guard against accidental regressions on either side of that
permission split, and would catch a future refactor that:

    * forgets to apply `IsAdminOrMatchingUser` to a new admin email
      endpoint,
    * accidentally requires authentication on the public unsubscribe
      endpoints, or
    * changes the `EMAILS_APP` settings keys and silently falls back to
      the (open) defaults.

Note: Django's `setup_test_environment()` flips `settings.DEBUG` to False,
which means the dev-only URLs registered conditionally on `settings.DEBUG`
inside `emails.api.dev_update_backend_emails` are NOT present during the
test run and therefore cannot be exercised here.  Those endpoints share
the exact same decorators as the regular admin endpoints, so the coverage
provided by the tests below is sufficient.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient

from emails.api.emails_config import EMAILS_CONFIG
from emails.app_settings import emails_settings
from emails.models import DynamicTemplate, EmailLog
from management.helpers import IsAdminOrMatchingUser
from management.models.settings import EmailSettings
from management.models.state import State
from management.models.user import User


def _first_template_name() -> str:
    """Return the name of any template registered in the emails config."""
    return next(iter(EMAILS_CONFIG.emails))


# A template name that is guaranteed not to exist; using it lets us exercise
# the permission gate of view functions whose successful path would require
# heavy context (real DB users, matches, etc.) to render an actual email.
NONEXISTENT_TEMPLATE = "permission-tests-nonexistent-template"


class EmailApiAdminPermissionTests(TestCase):
    """Verify every admin email endpoint enforces IsAdminOrMatchingUser."""

    @classmethod
    def setUpTestData(cls):
        cls.template_name = _first_template_name()

        cls.regular_user = User.objects.create_user(
            email="regular@example.com",
            password="Test123!",
            first_name="Regular",
            last_name="User",
        )

        cls.matching_user = User.objects.create_user(
            email="matcher@example.com",
            password="Test123!",
            first_name="Matching",
            last_name="User",
        )
        cls.matching_user.state.extra_user_permissions = [
            State.ExtraUserPermissionChoices.MATCHING_USER
        ]
        cls.matching_user.state.save()

        cls.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="Test123!",
            first_name="Admin",
            last_name="User",
        )
        cls.admin_user.is_staff = True
        cls.admin_user.save(update_fields=["is_staff"])

        cls.email_log = EmailLog.objects.create(
            log_version=1,
            template="permission-test",
            data={"html": "<p>hi</p>"},
        )

        cls.dynamic_template = DynamicTemplate.objects.create(
            template_name="permission-test-template",
            template="<p>Hello</p>",
            subject="Permission test",
            content={"foo": "bar"},
            category_id="dynamic",
            sender_id="noreply",
        )

    # ----------------------------------------------------------------- helpers

    def _client_for(self, user) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def _assert_forbidden_for_anon_and_regular(self, method: str, url: str, **kwargs):
        anon_response = getattr(self._client_for(None), method)(url, **kwargs)
        self.assertIn(
            anon_response.status_code,
            (401, 403),
            f"Anonymous request to {method.upper()} {url} should be rejected, got {anon_response.status_code}",
        )

        regular_response = getattr(self._client_for(self.regular_user), method)(url, **kwargs)
        self.assertEqual(
            regular_response.status_code,
            403,
            f"Regular user request to {method.upper()} {url} should be 403, got {regular_response.status_code}",
        )

    def _assert_allowed_for(self, user, method: str, url: str, **kwargs):
        response = getattr(self._client_for(user), method)(url, **kwargs)
        self.assertNotEqual(
            response.status_code,
            403,
            f"User {user.email} should pass permission check on {method.upper()} {url}, "
            f"got 403 (body={response.content!r})",
        )
        self.assertNotEqual(
            response.status_code,
            401,
            f"User {user.email} should be authenticated for {method.upper()} {url}, got 401",
        )

    def _assert_admin_or_matching_only(self, method: str, url: str, **kwargs):
        """
        Combined assertion: anon + regular user are rejected; admin + matching
        user pass the permission gate (response status may still be 4xx for
        validation/missing-resource, but it MUST NOT be 401/403).
        """
        self._assert_forbidden_for_anon_and_regular(method, url, **kwargs)
        self._assert_allowed_for(self.admin_user, method, url, **kwargs)
        self._assert_allowed_for(self.matching_user, method, url, **kwargs)

    # ------------------------------------------------------------ wiring tests

    def test_emails_settings_admin_permission_class_resolves_to_is_admin_or_matching_user(self):
        """
        The project must wire ADMIN_API_PERMISSION_CLASSES to the project's
        admin-or-matching-user permission, otherwise the admin email APIs
        fall back to the safe `IsAdminUser` default.
        """
        admin_perms = emails_settings.admin_api_permission_classes
        self.assertEqual(len(admin_perms), 1)
        self.assertIs(admin_perms[0], IsAdminOrMatchingUser)

    def test_emails_settings_public_permission_classes_stay_empty(self):
        """Public hash-based endpoints must not require authentication."""
        self.assertEqual(emails_settings.public_api_permission_classes, [])
        self.assertEqual(emails_settings.public_api_authentication_classes, [])

    def test_default_admin_permission_class_is_admin_only(self):
        """
        If a downstream project forgets to override ADMIN_API_PERMISSION_CLASSES
        the safe fallback must be admin-only — never `IsAuthenticated` or empty.
        """
        from rest_framework.permissions import IsAdminUser

        with override_settings(EMAILS_APP={}):
            classes = emails_settings.admin_api_permission_classes
            self.assertEqual(classes, [IsAdminUser])

    def test_default_normal_user_permission_class_is_authenticated(self):
        """The default 'normal user' tier must require authentication."""
        from rest_framework.permissions import IsAuthenticated

        with override_settings(EMAILS_APP={}):
            classes = emails_settings.api_permission_classes
            self.assertEqual(classes, [IsAuthenticated])

    # ------------------------------------------ admin endpoints (backend_templates)

    def test_email_config_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", "/api/matching/emails/config/")

    def test_list_templates_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", "/api/matching/emails/templates/")

    def test_show_template_info_endpoint_is_admin_only(self):
        # Use a non-existent template so the permitted-user branch returns
        # a clean 404 instead of trying to render a real template.
        self._assert_admin_or_matching_only(
            "get",
            f"/api/matching/emails/templates/{NONEXISTENT_TEMPLATE}/info/",
        )

    def test_render_backend_template_endpoint_is_admin_only(self):
        # Same trick: missing template -> 404 from the view body, but the
        # permission layer must still reject anon/regular users.
        self._assert_admin_or_matching_only(
            "get",
            f"/api/matching/emails/templates/{NONEXISTENT_TEMPLATE}/",
        )

    def test_render_logged_email_endpoint_is_admin_only(self):
        # Use a missing log id so the permitted branch raises EmailLog
        # DoesNotExist (5xx) - we only care that the permission gate is
        # not the thing rejecting admin/matching.
        url = f"/api/matching/emails/logs/{self.email_log.id}/"
        self._assert_forbidden_for_anon_and_regular("get", url)

        admin_resp = self._client_for(self.admin_user).get(url)
        self.assertNotIn(admin_resp.status_code, (401, 403))

        matcher_resp = self._client_for(self.matching_user).get(url)
        self.assertNotIn(matcher_resp.status_code, (401, 403))

    # -------------------------------------------------- admin endpoints (send_email)

    def test_send_template_email_endpoint_is_admin_only(self):
        # Patch out the actual mail sending so admin/matching paths don't try
        # to talk to SMTP, and ensure the patched callable returns a real
        # `Response` so DRF can finalise it.
        with patch("emails.api.send_email.send_template_email") as send_mock:
            send_mock.return_value = Response({"success": True})

            url = f"/api/matching/emails/templates/{self.template_name}/send/"
            payload = {"user_id": self.admin_user.id}

            self._assert_forbidden_for_anon_and_regular(
                "post", url, data=payload, format="json"
            )
            self._assert_allowed_for(
                self.admin_user, "post", url, data=payload, format="json"
            )
            self._assert_allowed_for(
                self.matching_user, "post", url, data=payload, format="json"
            )

    # --------------------------------------------- admin endpoints (dynamic_template)

    def test_dynamic_template_list_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", "/api/matching/emails/dynamic_templates/")

    def test_dynamic_template_retrieve_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only(
            "get",
            f"/api/matching/emails/dynamic_templates/{self.dynamic_template.template_name}/",
        )

    def test_dynamic_template_create_endpoint_blocks_non_admins(self):
        self._assert_forbidden_for_anon_and_regular(
            "post",
            "/api/matching/emails/dynamic_templates/",
            data={},
            format="json",
        )

    def test_dynamic_template_update_endpoint_blocks_non_admins(self):
        self._assert_forbidden_for_anon_and_regular(
            "patch",
            f"/api/matching/emails/dynamic_templates/{self.dynamic_template.template_name}/",
            data={},
            format="json",
        )

    def test_dynamic_template_send_endpoint_blocks_non_admins(self):
        self._assert_forbidden_for_anon_and_regular(
            "post",
            f"/api/matching/emails/dynamic_templates/{self.dynamic_template.template_name}/send/",
            data={"user_list": "all"},
            format="json",
        )

    # --------------------------------------------- public unsubscribe endpoints

    def test_public_email_settings_endpoints_remain_open_to_anonymous(self):
        """
        The hash-based unsubscribe endpoints are linked from inside emails and
        MUST keep working without any authentication.  We only assert that
        anonymous clients are not blocked by the permission layer (i.e. we
        never see a 401/403 - whatever the underlying view returns is fine).
        """
        email_settings = EmailSettings.objects.create()

        unsubscribable_categories = [
            category
            for category, cfg in EMAILS_CONFIG.categories.items()
            if cfg.unsubscribe
        ]
        category = unsubscribable_categories[0] if unsubscribable_categories else "dynamic"

        anon = self._client_for(None)

        retrieve_response = anon.get(f"/api/email_settings/{email_settings.hash}/")
        self.assertNotIn(retrieve_response.status_code, (401, 403))

        unsubscribe_response = anon.post(
            f"/api/email_settings/{email_settings.hash}/{category}/unsubscribe"
        )
        self.assertNotIn(unsubscribe_response.status_code, (401, 403))

        subscribe_response = anon.post(
            f"/api/email_settings/{email_settings.hash}/{category}/subscribe"
        )
        self.assertNotIn(subscribe_response.status_code, (401, 403))


class EmailApiDevOnlyPermissionWiringTests(TestCase):
    """
    The dev-only routes (`/overwrite/`, `/config/overwrite/`) are guarded by
    `if settings.DEBUG` at module import time.  Because Django's
    `setup_test_environment()` sets `settings.DEBUG = False` before the URL
    conf is first resolved during a test run, those URLs are NOT registered
    here.  Instead of fighting that, we verify the wiring at the function
    object level: the views still carry the admin-only decorators they
    inherit from `emails_settings.admin_api_permission_classes`.
    """

    def test_overwrite_backend_template_view_uses_admin_permission_classes(self):
        from emails.api.dev_update_backend_emails import overwrite_backend_template

        view_class = overwrite_backend_template.cls
        self.assertEqual(view_class.permission_classes, [IsAdminOrMatchingUser])

    def test_update_config_json_view_uses_admin_permission_classes(self):
        from emails.api.dev_update_backend_emails import update_config_json

        view_class = update_config_json.cls
        self.assertEqual(view_class.permission_classes, [IsAdminOrMatchingUser])
