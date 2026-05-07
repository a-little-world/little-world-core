"""
Permission tests for the emails django module.

Admin endpoints must enforce IsAdminOrMatchingUser (staff or MATCHING_USER perm),
public hash-based unsubscribe endpoints must stay open to anonymous clients.

Note: Django's setup_test_environment() flips settings.DEBUG to False, so the
DEBUG-only routes in dev_update_backend_emails are not registered during tests
and are covered via attribute-level checks instead.
"""

from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from emails.api.emails_config import EMAILS_CONFIG
from emails.app_settings import emails_settings
from emails.models import DynamicTemplate, EmailLog
from rest_framework.response import Response
from rest_framework.test import APIClient

from management.helpers import IsAdminOrMatchingUser
from management.models.settings import EmailSettings
from management.models.user import User
from management.permissions import ManagementPermission


def _first_template_name() -> str:
    return next(iter(EMAILS_CONFIG.emails))


# guaranteed to not exist; lets us hit the permission gate without rendering a real email
NONEXISTENT_TEMPLATE = "permission-tests-nonexistent-template"


class EmailApiAdminPermissionTests(TestCase):
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
        permission = Permission.objects.filter(
            content_type__app_label="management",
            content_type__model="state",
            codename=ManagementPermission.MATCHING_USER.codename,
        ).first()
        if permission is not None:
            cls.matching_user.user_permissions.add(permission)

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

    def _client_for(self, user) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def _assert_forbidden_for_anon_and_regular(self, method: str, url: str, **kwargs):
        anon_response = getattr(self._client_for(None), method)(url, **kwargs)
        self.assertIn(anon_response.status_code, (401, 403))

        regular_response = getattr(self._client_for(self.regular_user), method)(url, **kwargs)
        self.assertEqual(regular_response.status_code, 403)

    def _assert_allowed_for(self, user, method: str, url: str, **kwargs):
        response = getattr(self._client_for(user), method)(url, **kwargs)
        self.assertNotIn(response.status_code, (401, 403))

    def _assert_admin_or_matching_only(self, method: str, url: str, **kwargs):
        # response may still be 4xx for missing data, but never 401/403 for permitted users
        self._assert_forbidden_for_anon_and_regular(method, url, **kwargs)
        self._assert_allowed_for(self.admin_user, method, url, **kwargs)
        self._assert_allowed_for(self.matching_user, method, url, **kwargs)

    # wiring

    def test_admin_permission_class_resolves_to_is_admin_or_matching_user(self):
        admin_perms = emails_settings.admin_api_permission_classes
        self.assertEqual(len(admin_perms), 1)
        self.assertIs(admin_perms[0], IsAdminOrMatchingUser)

    def test_public_permission_classes_stay_empty(self):
        self.assertEqual(emails_settings.public_api_permission_classes, [])
        self.assertEqual(emails_settings.public_api_authentication_classes, [])

    def test_default_admin_permission_class_is_admin_only(self):
        from rest_framework.permissions import IsAdminUser

        with override_settings(EMAILS_APP={}):
            self.assertEqual(emails_settings.admin_api_permission_classes, [IsAdminUser])

    def test_default_normal_user_permission_class_is_authenticated(self):
        from rest_framework.permissions import IsAuthenticated

        with override_settings(EMAILS_APP={}):
            self.assertEqual(emails_settings.api_permission_classes, [IsAuthenticated])

    # backend_templates

    def test_email_config_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", "/api/matching/emails/config/")

    def test_list_templates_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", "/api/matching/emails/templates/")

    def test_show_template_info_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", f"/api/matching/emails/templates/{NONEXISTENT_TEMPLATE}/info/")

    def test_render_backend_template_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", f"/api/matching/emails/templates/{NONEXISTENT_TEMPLATE}/")

    def test_render_logged_email_endpoint_is_admin_only(self):
        url = f"/api/matching/emails/logs/{self.email_log.id}/"
        self._assert_forbidden_for_anon_and_regular("get", url)
        self._assert_allowed_for(self.admin_user, "get", url)
        self._assert_allowed_for(self.matching_user, "get", url)

    # send_email

    def test_send_template_email_endpoint_is_admin_only(self):
        with patch("emails.api.send_email.send_template_email") as send_mock:
            send_mock.return_value = Response({"success": True})

            url = f"/api/matching/emails/templates/{self.template_name}/send/"
            payload = {"user_id": self.admin_user.id}

            self._assert_forbidden_for_anon_and_regular("post", url, data=payload, format="json")
            self._assert_allowed_for(self.admin_user, "post", url, data=payload, format="json")
            self._assert_allowed_for(self.matching_user, "post", url, data=payload, format="json")

    # dynamic_template

    def test_dynamic_template_list_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only("get", "/api/matching/emails/dynamic_templates/")

    def test_dynamic_template_retrieve_endpoint_is_admin_only(self):
        self._assert_admin_or_matching_only(
            "get",
            f"/api/matching/emails/dynamic_templates/{self.dynamic_template.template_name}/",
        )

    def test_dynamic_template_create_endpoint_blocks_non_admins(self):
        self._assert_forbidden_for_anon_and_regular(
            "post", "/api/matching/emails/dynamic_templates/", data={}, format="json"
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

    # public unsubscribe endpoints

    def test_public_email_settings_endpoints_remain_open_to_anonymous(self):
        email_settings = EmailSettings.objects.create()
        unsubscribable = [c for c, cfg in EMAILS_CONFIG.categories.items() if cfg.unsubscribe]
        category = unsubscribable[0] if unsubscribable else "dynamic"

        anon = self._client_for(None)

        retrieve = anon.get(f"/api/email_settings/{email_settings.hash}/")
        self.assertNotIn(retrieve.status_code, (401, 403))

        unsubscribe = anon.post(f"/api/email_settings/{email_settings.hash}/{category}/unsubscribe")
        self.assertNotIn(unsubscribe.status_code, (401, 403))

        subscribe = anon.post(f"/api/email_settings/{email_settings.hash}/{category}/subscribe")
        self.assertNotIn(subscribe.status_code, (401, 403))


class EmailApiDevOnlyPermissionWiringTests(TestCase):
    # DEBUG-only urlpatterns are stripped during tests, so we check the decorator wiring directly

    def test_overwrite_backend_template_view_uses_admin_permission_classes(self):
        from emails.api.dev_update_backend_emails import overwrite_backend_template

        self.assertEqual(overwrite_backend_template.cls.permission_classes, [IsAdminOrMatchingUser])

    def test_update_config_json_view_uses_admin_permission_classes(self):
        from emails.api.dev_update_backend_emails import update_config_json

        self.assertEqual(update_config_json.cls.permission_classes, [IsAdminOrMatchingUser])
