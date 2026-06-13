from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from management.models.open_chat_configuration import OpenChatConfiguration
from management.models.user import User
from management.permissions import ManagementPermission

API_URL = "/api/matching/open-chat-configuration/"


class OpenChatConfigurationApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.api_client = APIClient()
        content_type = ContentType.objects.get(app_label="management", model="state")

        def ensure_permission(codename: str) -> Permission:
            permission, _ = Permission.objects.get_or_create(
                codename=codename,
                content_type=content_type,
                defaults={"name": codename},
            )
            return permission

        cls.open_chat_perm = ensure_permission(ManagementPermission.OPEN_CHAT_ACCESS.codename)
        cls.edit_open_chat_perm = ensure_permission(
            ManagementPermission.EDIT_OPEN_CHAT_CONFIGURATION.codename
        )
        cls.matching_perm = ensure_permission(ManagementPermission.MATCHING_USER.codename)

        cls.authorized_user = User.objects.create_user(
            email="open-chat-user@test.de",
            username="open-chat-user@test.de",
            password="Test123!",
            first_name="Open",
            last_name="Chat",
        )
        cls.authorized_user.user_permissions.add(cls.open_chat_perm, cls.edit_open_chat_perm)

        cls.view_only_user = User.objects.create_user(
            email="open-chat-view-only@test.de",
            username="open-chat-view-only@test.de",
            password="Test123!",
            first_name="View",
            last_name="Only",
        )
        cls.view_only_user.user_permissions.add(cls.open_chat_perm)

        cls.unauthorized_user = User.objects.create_user(
            email="no-open-chat-user@test.de",
            username="no-open-chat-user@test.de",
            password="Test123!",
            first_name="No",
            last_name="Access",
        )
        cls.unauthorized_user.user_permissions.add(cls.matching_perm)

    def test_get_requires_open_chat_permission(self):
        self.api_client.force_authenticate(user=self.unauthorized_user)
        response = self.api_client.get(API_URL)
        self.assertEqual(response.status_code, 403)

    def test_get_returns_404_when_missing(self):
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.get(API_URL)
        self.assertEqual(response.status_code, 404)

    def test_view_only_user_can_get_configuration(self):
        OpenChatConfiguration.objects.create(
            user=self.view_only_user,
            open_chat_api_key="view-only-key",
            open_chat_user="view-only-user",
        )
        self.api_client.force_authenticate(user=self.view_only_user)
        response = self.api_client.get(API_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["open_chat_user"], "view-only-user")

    def test_post_requires_edit_permission(self):
        self.api_client.force_authenticate(user=self.view_only_user)
        response = self.api_client.post(
            API_URL,
            {"open_chat_api_key": "test-api-key", "open_chat_user": "test-open-chat-user"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_put_requires_edit_permission(self):
        OpenChatConfiguration.objects.create(
            user=self.view_only_user,
            open_chat_api_key="existing-key",
            open_chat_user="existing-user",
        )
        self.api_client.force_authenticate(user=self.view_only_user)
        response = self.api_client.put(
            API_URL,
            {"open_chat_api_key": "updated-key", "open_chat_user": "updated-user"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_post_creates_configuration(self):
        self.api_client.force_authenticate(user=self.authorized_user)
        payload = {
            "open_chat_api_key": "test-api-key",
            "open_chat_user": "test-open-chat-user",
        }
        response = self.api_client.post(API_URL, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, payload)
        configuration = OpenChatConfiguration.objects.get(user=self.authorized_user)
        self.assertEqual(configuration.open_chat_api_key, payload["open_chat_api_key"])
        self.assertEqual(configuration.open_chat_user, payload["open_chat_user"])

    def test_post_rejects_duplicate_configuration(self):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="existing-key",
            open_chat_user="existing-user",
        )
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(
            API_URL,
            {"open_chat_api_key": "new-key", "open_chat_user": "new-user"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)

    def test_post_ignores_user_field_in_payload(self):
        other_user = User.objects.create_user(
            email="other-open-chat-user@test.de",
            username="other-open-chat-user@test.de",
            password="Test123!",
            first_name="Other",
            last_name="User",
        )
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(
            API_URL,
            {
                "user": other_user.id,
                "open_chat_api_key": "owned-key",
                "open_chat_user": "owned-user",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        configuration = OpenChatConfiguration.objects.get(user=self.authorized_user)
        self.assertEqual(configuration.user_id, self.authorized_user.id)

    def test_put_updates_configuration(self):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="old-key",
            open_chat_user="old-user",
        )
        self.api_client.force_authenticate(user=self.authorized_user)
        payload = {
            "open_chat_api_key": "updated-key",
            "open_chat_user": "updated-user",
        }
        response = self.api_client.put(API_URL, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)
        configuration = OpenChatConfiguration.objects.get(user=self.authorized_user)
        self.assertEqual(configuration.open_chat_api_key, payload["open_chat_api_key"])
        self.assertEqual(configuration.open_chat_user, payload["open_chat_user"])

    def test_put_returns_404_when_missing(self):
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.put(
            API_URL,
            {"open_chat_api_key": "key", "open_chat_user": "user"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_users_cannot_read_other_users_configuration(self):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="secret-key",
            open_chat_user="secret-user",
        )
        other_authorized_user = User.objects.create_user(
            email="other-authorized@test.de",
            username="other-authorized@test.de",
            password="Test123!",
            first_name="Other",
            last_name="Authorized",
        )
        other_authorized_user.user_permissions.add(self.open_chat_perm)
        self.api_client.force_authenticate(user=other_authorized_user)
        response = self.api_client.get(API_URL)
        self.assertEqual(response.status_code, 404)
