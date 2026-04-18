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
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from emails.api.emails_config import EMAILS_CONFIG
from emails.app_settings import emails_settings
from emails.models import DynamicTemplate, EmailLog
from rest_framework.test import APIClient

from management.helpers import IsAdminOrMatchingUser
from management.models.settings import EmailSettings
from management.models.state import State
from management.models.user import User


def _first_template_name() -> str:
    """Return the name of any template registered in the emails config."""
    return next(iter(EMAILS_CONFIG.emails))


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
        cls.matching_user.state.extra_user_permissions = [State.ExtraUserPermissionChoices.MATCHING_USER]
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
        validation errors, but it MUST NOT be 401/403).
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
        self._assert_admin_or_matching_only(
            "get",
            f"/api/matching/emails/templates/{self.template_name}/info/",
        )

    def test_render_backend_template_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only(
            "get",
            f"/api/matching/emails/templates/{self.template_name}/",
        )

    def test_render_logged_email_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only(
            "get",
            f"/api/matching/emails/logs/{self.email_log.id}/",
        )

    # -------------------------------------------------- admin endpoints (send_email)

    def test_send_template_email_endpoint_is_admin_only(self):
        # Patch out actual mail sending so we don't hit SMTP just because the
        # admin/matching user passes the permission check.
        with patch("emails.api.send_email.send_template_email") as send_mock:
            send_mock.return_value = None  # unused for the rejection branches
            self._assert_forbidden_for_anon_and_regular(
                "post",
                f"/api/matching/emails/templates/{self.template_name}/send/",
                data={"user_id": self.admin_user.id},
                format="json",
            )
            self._assert_allowed_for(
                self.admin_user,
                "post",
                f"/api/matching/emails/templates/{self.template_name}/send/",
                data={"user_id": self.admin_user.id},
                format="json",
            )
            self._assert_allowed_for(
                self.matching_user,
                "post",
                f"/api/matching/emails/templates/{self.template_name}/send/",
                data={"user_id": self.admin_user.id},
                format="json",
            )

    # --------------------------------------------- admin endpoints (dynamic_template)

    def test_dynamic_template_list_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", "/api/matching/emails/dynamic_templates/")

    def test_dynamic_template_retrieve_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only(
            "get",
            f"/api/matching/emails/dynamic_templates/{self.dynamic_template.template_name}/",
        )

    def test_dynamic_template_create_endpoint_is_admin_only(self):
        self._assert_forbidden_for_anon_and_regular(
            "post",
            "/api/matching/emails/dynamic_templates/",
            data={},
            format="json",
        )

    def test_dynamic_template_update_endpoint_is_admin_only(self):
        self._assert_forbidden_for_anon_and_regular(
            "patch",
            f"/api/matching/emails/dynamic_templates/{self.dynamic_template.template_name}/",
            data={},
            format="json",
        )

    def test_dynamic_template_send_endpoint_is_admin_only(self):
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

        # Make sure there's at least one un-subscribable category to use.
        unsubscribable_categories = [category for category, cfg in EMAILS_CONFIG.categories.items() if cfg.unsubscribe]
        category = unsubscribable_categories[0] if unsubscribable_categories else "dynamic"

        anon = self._client_for(None)

        retrieve_response = anon.get(f"/api/email_settings/{email_settings.hash}/")
        self.assertNotIn(retrieve_response.status_code, (401, 403))

        unsubscribe_response = anon.post(f"/api/email_settings/{email_settings.hash}/{category}/unsubscribe")
        self.assertNotIn(unsubscribe_response.status_code, (401, 403))

        subscribe_response = anon.post(f"/api/email_settings/{email_settings.hash}/{category}/subscribe")
        self.assertNotIn(subscribe_response.status_code, (401, 403))


class EmailApiAdminPermissionDebugOnlyTests(TestCase):
    """
    Extra coverage for the dev-only endpoints that are wired up to
    `admin_api_*` settings as well, so a non-admin can never edit the
    backend templates / config even when DEBUG is true.
    """

    @classmethod
    def setUpTestData(cls):
        cls.template_name = _first_template_name()
        cls.regular_user = User.objects.create_user(
            email="regular-debug@example.com",
            password="Test123!",
            first_name="Regular",
            last_name="Debug",
        )

    def test_overwrite_backend_template_blocks_non_admins(self):
        # DEBUG-only urlpatterns: only run the assertion when the route is
        # actually registered to avoid spurious 404s.
        from django.urls import NoReverseMatch, get_resolver

        try:
            get_resolver().resolve(f"/api/matching/emails/templates/{self.template_name}/overwrite/")
        except Exception:
            self.skipTest("dev-only endpoint not registered (DEBUG is False)")
            return  # for type checkers; skipTest raises

        client = APIClient()
        anon_response = client.post(
            f"/api/matching/emails/templates/{self.template_name}/overwrite/",
            data={"html": "<p>x</p>"},
            format="json",
        )
        self.assertIn(anon_response.status_code, (401, 403))

        client.force_authenticate(user=self.regular_user)
        regular_response = client.post(
            f"/api/matching/emails/templates/{self.template_name}/overwrite/",
            data={"html": "<p>x</p>"},
            format="json",
        )
        self.assertEqual(regular_response.status_code, 403)

        # Reference NoReverseMatch so flake8/pyright don't complain about the
        # unused import in environments without the debug routes.
        _ = NoReverseMatch

    def test_update_config_json_blocks_non_admins(self):
        from django.urls import get_resolver

        try:
            get_resolver().resolve("/api/matching/emails/config/overwrite/")
        except Exception:
            self.skipTest("dev-only endpoint not registered (DEBUG is False)")
            return

        client = APIClient()
        anon_response = client.post(
            "/api/matching/emails/config/overwrite/",
            data={},
            format="json",
        )
        self.assertIn(anon_response.status_code, (401, 403))

        client.force_authenticate(user=self.regular_user)
        regular_response = client.post(
            "/api/matching/emails/config/overwrite/",
            data={},
            format="json",
        )
        self.assertEqual(regular_response.status_code, 403)
