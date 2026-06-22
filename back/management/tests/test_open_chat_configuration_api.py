from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from management.models.matches import Match
from management.models.open_chat_configuration import DEFAULT_OPEN_CHAT_HOST, OpenChatConfiguration
from management.models.user import User
from management.permissions import ManagementPermission

API_URL = "/api/matching/open-chat-configuration/"
TEST_CONNECTION_URL = "/api/matching/open-chat/test-connection/"
ACCESS_USERS_URL = "/api/matching/open-chat-access-users/"
USER_CONFIGURATION_URL = "/api/matching/open-chat-access-users/{user_id}/configuration/"
CREATE_MATCHING_URL = "/api/matching/open-chat-access-users/{user_id}/create-matching/"
DEFAULT_HOST = DEFAULT_OPEN_CHAT_HOST


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
        cls.edit_open_chat_perm = ensure_permission(ManagementPermission.EDIT_OPEN_CHAT_CONFIGURATION.codename)
        cls.manage_open_chat_perm = ensure_permission(ManagementPermission.MANAGE_OPEN_CHAT_ACCESS.codename)
        cls.matching_perm = ensure_permission(ManagementPermission.MATCHING_USER.codename)

        cls.authorized_user = User.objects.create_user(
            email="open-chat-user@test.de",
            username="open-chat-user@test.de",
            password="Test123!",
            first_name="Open",
            last_name="Chat",
        )
        cls.authorized_user.user_permissions.add(cls.open_chat_perm, cls.edit_open_chat_perm)

        cls.manager_user = User.objects.create_user(
            email="open-chat-manager@test.de",
            username="open-chat-manager@test.de",
            password="Test123!",
            first_name="Open",
            last_name="Manager",
        )
        cls.manager_user.user_permissions.add(
            cls.open_chat_perm,
            cls.manage_open_chat_perm,
        )

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
            open_chat_host=DEFAULT_HOST,
        )
        self.api_client.force_authenticate(user=self.view_only_user)
        response = self.api_client.get(API_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["open_chat_user"], "view-only-user")
        self.assertEqual(response.data["open_chat_host"], DEFAULT_HOST)

    def test_post_requires_edit_permission(self):
        self.api_client.force_authenticate(user=self.view_only_user)
        response = self.api_client.post(
            API_URL,
            {
                "open_chat_api_key": "test-api-key",
                "open_chat_user": "test-open-chat-user",
                "open_chat_host": DEFAULT_HOST,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_put_requires_edit_permission(self):
        OpenChatConfiguration.objects.create(
            user=self.view_only_user,
            open_chat_api_key="existing-key",
            open_chat_user="existing-user",
            open_chat_host=DEFAULT_HOST,
        )
        self.api_client.force_authenticate(user=self.view_only_user)
        response = self.api_client.put(
            API_URL,
            {
                "open_chat_api_key": "updated-key",
                "open_chat_user": "updated-user",
                "open_chat_host": "https://updated.example.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_post_creates_configuration(self):
        self.api_client.force_authenticate(user=self.authorized_user)
        payload = {
            "open_chat_api_key": "test-api-key",
            "open_chat_user": "test-open-chat-user",
            "open_chat_host": DEFAULT_HOST,
        }
        response = self.api_client.post(API_URL, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, payload)
        configuration = OpenChatConfiguration.objects.get(user=self.authorized_user)
        self.assertEqual(configuration.open_chat_api_key, payload["open_chat_api_key"])
        self.assertEqual(configuration.open_chat_user, payload["open_chat_user"])
        self.assertEqual(configuration.open_chat_host, payload["open_chat_host"])

    def test_post_rejects_duplicate_configuration(self):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="existing-key",
            open_chat_user="existing-user",
            open_chat_host=DEFAULT_HOST,
        )
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(
            API_URL,
            {
                "open_chat_api_key": "new-key",
                "open_chat_user": "new-user",
                "open_chat_host": DEFAULT_HOST,
            },
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
                "open_chat_host": DEFAULT_HOST,
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
            open_chat_host=DEFAULT_HOST,
        )
        self.api_client.force_authenticate(user=self.authorized_user)
        payload = {
            "open_chat_api_key": "updated-key",
            "open_chat_user": "updated-user",
            "open_chat_host": "https://updated.example.com",
        }
        response = self.api_client.put(API_URL, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)
        configuration = OpenChatConfiguration.objects.get(user=self.authorized_user)
        self.assertEqual(configuration.open_chat_api_key, payload["open_chat_api_key"])
        self.assertEqual(configuration.open_chat_user, payload["open_chat_user"])
        self.assertEqual(configuration.open_chat_host, payload["open_chat_host"])

    def test_put_returns_404_when_missing(self):
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.put(
            API_URL,
            {
                "open_chat_api_key": "key",
                "open_chat_user": "user",
                "open_chat_host": DEFAULT_HOST,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_users_cannot_read_other_users_configuration(self):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="secret-key",
            open_chat_user="secret-user",
            open_chat_host=DEFAULT_HOST,
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

    def test_test_connection_requires_open_chat_permission(self):
        self.api_client.force_authenticate(user=self.unauthorized_user)
        response = self.api_client.post(TEST_CONNECTION_URL, {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_test_connection_returns_404_without_configuration(self):
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(TEST_CONNECTION_URL, {}, format="json")
        self.assertEqual(response.status_code, 404)

    @patch("management.api.open_chat._build_open_chat_client")
    def test_test_connection_success(self, mock_build_client):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="test-api-key",
            open_chat_user="test-open-chat-user",
            open_chat_host=DEFAULT_HOST,
        )
        mock_client = MagicMock()
        mock_client.login.return_value = {"name": "Test User"}
        mock_build_client.return_value = mock_client

        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(TEST_CONNECTION_URL, {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user_name"], "Test User")
        mock_build_client.assert_called_once_with(
            host=DEFAULT_HOST,
            username="test-open-chat-user",
            password="test-api-key",
        )
        mock_client.login.assert_called_once()

    def test_access_users_requires_manage_permission(self):
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.get(ACCESS_USERS_URL)
        self.assertEqual(response.status_code, 403)

    def test_access_users_lists_open_chat_permission_holders(self):
        OpenChatConfiguration.objects.create(
            user=self.view_only_user,
            open_chat_api_key="view-only-key",
            open_chat_user="view-only-user",
            open_chat_host=DEFAULT_HOST,
        )
        self.api_client.force_authenticate(user=self.manager_user)
        response = self.api_client.get(ACCESS_USERS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)

        by_email = {entry["email"]: entry for entry in response.data}
        self.assertIn(self.view_only_user.email, by_email)
        self.assertIn(self.authorized_user.email, by_email)
        self.assertIn(self.manager_user.email, by_email)
        self.assertEqual(
            by_email[self.view_only_user.email]["configuration"],
            {
                "open_chat_api_key": "view-only-key",
                "open_chat_user": "view-only-user",
                "open_chat_host": DEFAULT_HOST,
            },
        )
        self.assertIsNone(by_email[self.authorized_user.email]["configuration"])
        self.assertNotIn(self.unauthorized_user.email, by_email)

    def test_user_configuration_requires_manage_permission(self):
        url = USER_CONFIGURATION_URL.format(user_id=self.view_only_user.id)
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.put(
            url,
            {
                "open_chat_api_key": "updated-key",
                "open_chat_user": "updated-user",
                "open_chat_host": DEFAULT_HOST,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_user_configuration_create_and_update(self):
        create_url = USER_CONFIGURATION_URL.format(user_id=self.authorized_user.id)
        payload = {
            "open_chat_api_key": "managed-key",
            "open_chat_user": "managed-user",
            "open_chat_host": DEFAULT_HOST,
        }
        self.api_client.force_authenticate(user=self.manager_user)

        response = self.api_client.post(create_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, payload)

        update_payload = {
            "open_chat_api_key": "managed-key-updated",
            "open_chat_user": "managed-user-updated",
            "open_chat_host": "https://updated.example.com",
        }
        response = self.api_client.put(create_url, update_payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, update_payload)

        configuration = OpenChatConfiguration.objects.get(user=self.authorized_user)
        self.assertEqual(configuration.open_chat_api_key, update_payload["open_chat_api_key"])
        self.assertEqual(configuration.open_chat_user, update_payload["open_chat_user"])
        self.assertEqual(configuration.open_chat_host, update_payload["open_chat_host"])

    def test_user_configuration_rejects_non_open_chat_users(self):
        url = USER_CONFIGURATION_URL.format(user_id=self.unauthorized_user.id)
        self.api_client.force_authenticate(user=self.manager_user)
        response = self.api_client.post(
            url,
            {
                "open_chat_api_key": "managed-key",
                "open_chat_user": "managed-user",
                "open_chat_host": DEFAULT_HOST,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_access_users_includes_matching_exists_with_manager(self):
        self.api_client.force_authenticate(user=self.manager_user)
        response = self.api_client.get(ACCESS_USERS_URL)
        self.assertEqual(response.status_code, 200)

        by_email = {entry["email"]: entry for entry in response.data}
        self.assertIsNone(by_email[self.manager_user.email]["matching_exists"])
        self.assertFalse(by_email[self.view_only_user.email]["matching_exists"])

        Match.objects.create(
            user1=self.manager_user,
            user2=self.view_only_user,
            active=True,
            confirmed=True,
            support_matching=True,
        )

        response = self.api_client.get(ACCESS_USERS_URL)
        by_email = {entry["email"]: entry for entry in response.data}
        self.assertTrue(by_email[self.view_only_user.email]["matching_exists"])

    def test_create_matching_requires_manage_permission(self):
        url = CREATE_MATCHING_URL.format(user_id=self.view_only_user.id)
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_create_matching_creates_silent_match(self):
        url = CREATE_MATCHING_URL.format(user_id=self.view_only_user.id)
        self.api_client.force_authenticate(user=self.manager_user)
        response = self.api_client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["matching_exists"])
        self.assertTrue(
            Match.get_match(self.manager_user, self.view_only_user).exists(),
        )

    def test_create_matching_rejects_existing_match(self):
        Match.objects.create(
            user1=self.manager_user,
            user2=self.view_only_user,
            active=True,
            confirmed=True,
            support_matching=True,
        )
        url = CREATE_MATCHING_URL.format(user_id=self.view_only_user.id)
        self.api_client.force_authenticate(user=self.manager_user)
        response = self.api_client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.data["matching_exists"])
