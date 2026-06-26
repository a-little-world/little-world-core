from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from chat.models import Chat
from client import PasswordAuth
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from management.models.matches import Match
from management.models.open_chat_configuration import DEFAULT_OPEN_CHAT_HOST, OpenChatConfiguration
from management.models.support_task import SupportTask
from management.models.user import User
from management.permissions import ManagementPermission

API_URL = "/api/matching/open-chat-configuration/"
TEST_CONNECTION_URL = "/api/matching/open-chat/test-connection/"
ACCESS_USERS_URL = "/api/matching/open-chat-access-users/"
USER_CONFIGURATION_URL = "/api/matching/open-chat-access-users/{user_id}/configuration/"
CREATE_MATCHING_URL = "/api/matching/open-chat-access-users/{user_id}/create-matching/"
INTERACTIONS_URL = "/api/matching/open-chat/interactions/"
INTERACTION_DETAIL_URL = "/api/matching/open-chat/interactions/{interaction_uuid}/"
DELETE_CHAT_URL = "/api/matching/open-chat/chats/{chat_uuid}/"
AUTOMATION_GENERATE_MESSAGE_REPLIES_URL = "/api/matching/open-chat/automation-triggers/generate-message-replies/"
AUTOMATION_CLEAR_MESSAGE_REPLIES_URL = "/api/matching/open-chat/automation-triggers/generate-message-replies/clear/"
IDEMPOTENT_ACTIONS_URL = "/api/matching/open-chat/idempotent-actions/"
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

        cls.manage_only_user = User.objects.create_user(
            email="open-chat-manage-only@test.de",
            username="open-chat-manage-only@test.de",
            password="Test123!",
            first_name="Manage",
            last_name="Only",
        )
        cls.manage_only_user.user_permissions.add(cls.manage_open_chat_perm)

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

    @patch("management.api.open_chat.OpenChatClient")
    def test_test_connection_success(self, mock_build_client):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="test-api-key",
            open_chat_user="test-open-chat-user",
            open_chat_host=DEFAULT_HOST,
        )
        mock_client = MagicMock()
        mock_client.login.return_value = SimpleNamespace(name="Test User")
        mock_build_client.return_value = mock_client

        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(TEST_CONNECTION_URL, {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user_name"], "Test User")
        mock_build_client.assert_called_once_with(
            base_url=DEFAULT_HOST,
            auth=PasswordAuth(email="test-open-chat-user", password="test-api-key"),
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

    @patch("management.api.open_chat.OpenChatClient")
    def test_interactions_returns_interactions_for_current_user(self, mock_build_client):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="test-api-key",
            open_chat_user="test-open-chat-user",
            open_chat_host=DEFAULT_HOST,
        )
        mock_client = MagicMock()
        mock_client.get_interactions.return_value = SimpleNamespace(
            rows=[
                SimpleNamespace(
                    uuid="interaction-1",
                    title="First interaction",
                    status="completed",
                    created=None,
                    updated=None,
                    shared_interaction_url=None,
                )
            ]
        )
        mock_build_client.return_value = mock_client

        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.get(INTERACTIONS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["interaction_id"], "interaction-1")
        self.assertEqual(response.data["results"][0]["title"], "First interaction")
        mock_client.login.assert_called_once()
        mock_client.get_interactions.assert_called()

    @patch("management.api.open_chat.OpenChatClient")
    def test_interactions_manager_can_query_other_user_by_uuid(self, mock_build_client):
        OpenChatConfiguration.objects.create(
            user=self.view_only_user,
            open_chat_api_key="view-only-key",
            open_chat_user="view-only-user",
            open_chat_host=DEFAULT_HOST,
        )
        mock_client = MagicMock()
        mock_client.get_interactions.return_value = SimpleNamespace(
            rows=[
                SimpleNamespace(
                    uuid="42",
                    title="Managed interaction",
                    status=None,
                    created=None,
                    updated=None,
                    shared_interaction_url=None,
                )
            ]
        )
        mock_build_client.return_value = mock_client

        self.api_client.force_authenticate(user=self.manager_user)
        response = self.api_client.get(
            INTERACTIONS_URL,
            {"user_uuid": str(self.view_only_user.uuid)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["interaction_id"], "42")
        self.assertEqual(response.data["results"][0]["title"], "Managed interaction")
        mock_build_client.assert_called_once_with(
            base_url=DEFAULT_HOST,
            auth=PasswordAuth(email="view-only-user", password="view-only-key"),
        )

    @patch("management.api.open_chat.OpenChatClient")
    def test_interactions_non_manager_ignores_other_user_uuid(self, mock_build_client):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="authorized-key",
            open_chat_user="authorized-user",
            open_chat_host=DEFAULT_HOST,
        )
        mock_client = MagicMock()
        mock_client.get_interactions.return_value = SimpleNamespace(
            rows=[
                SimpleNamespace(
                    uuid="interaction-own-config",
                    title=None,
                    status=None,
                    created=None,
                    updated=None,
                    shared_interaction_url=None,
                )
            ]
        )
        mock_build_client.return_value = mock_client

        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.get(
            INTERACTIONS_URL,
            {"user_uuid": str(self.view_only_user.uuid)},
        )
        self.assertEqual(response.status_code, 200)
        mock_build_client.assert_called_once_with(
            base_url=DEFAULT_HOST,
            auth=PasswordAuth(email="authorized-user", password="authorized-key"),
        )

    @patch("management.api.open_chat.OpenChatClient")
    def test_interactions_manage_only_user_can_query_other_user(self, mock_build_client):
        OpenChatConfiguration.objects.create(
            user=self.view_only_user,
            open_chat_api_key="view-only-key",
            open_chat_user="view-only-user",
            open_chat_host=DEFAULT_HOST,
        )
        mock_client = MagicMock()
        mock_client.get_interactions.return_value = SimpleNamespace(
            rows=[
                SimpleNamespace(
                    uuid="interaction-manage-only",
                    title=None,
                    status=None,
                    created=None,
                    updated=None,
                    shared_interaction_url=None,
                )
            ]
        )
        mock_build_client.return_value = mock_client

        self.api_client.force_authenticate(user=self.manage_only_user)
        response = self.api_client.get(
            INTERACTIONS_URL,
            {"user_uuid": str(self.view_only_user.uuid)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["interaction_id"], "interaction-manage-only")

    @patch("management.api.open_chat.OpenChatClient")
    def test_interaction_detail_returns_interaction(self, mock_build_client):
        interaction_uuid = "6ece98ca-8d5c-4791-a198-0b971c0ac0d6"
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="authorized-key",
            open_chat_user="authorized-user",
            open_chat_host=DEFAULT_HOST,
        )
        mock_client = MagicMock()
        mock_client.get_interaction.return_value = SimpleNamespace(
            uuid=interaction_uuid,
            title="Detailed interaction",
            status="completed",
            created=None,
            updated=None,
            shared_interaction_url=None,
            to_dict=lambda: {
                "uuid": interaction_uuid,
                "title": "Detailed interaction",
                "status": "completed",
                "created": None,
                "updated": None,
                "shared_interaction_url": None,
            },
        )
        mock_build_client.return_value = mock_client

        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.get(
            INTERACTION_DETAIL_URL.format(interaction_uuid=interaction_uuid),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["interaction_id"], interaction_uuid)
        self.assertEqual(response.data["title"], "Detailed interaction")
        mock_client.get_interaction.assert_called_once_with(interaction_uuid)

    def test_delete_chat_deletes_owned_open_chat_chat(self):
        chat = Chat.objects.create(
            u1=self.authorized_user,
            u2=self.view_only_user,
            is_temporary=False,
        )
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.delete(
            DELETE_CHAT_URL.format(chat_uuid=chat.uuid),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Chat.objects.filter(pk=chat.pk).exists())

    def test_delete_chat_returns_404_for_non_participant(self):
        chat = Chat.objects.create(
            u1=self.view_only_user,
            u2=self.manager_user,
            is_temporary=False,
        )
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.delete(
            DELETE_CHAT_URL.format(chat_uuid=chat.uuid),
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_chat_rejects_non_open_chat_partner(self):
        chat = Chat.objects.create(
            u1=self.authorized_user,
            u2=self.unauthorized_user,
            is_temporary=False,
        )
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.delete(
            DELETE_CHAT_URL.format(chat_uuid=chat.uuid),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("management.api.open_chat.idempotent_actions__generate_message_replies.delay")
    def test_automation_generate_message_replies_enqueues_task(self, mock_delay):
        OpenChatConfiguration.objects.create(
            user=self.authorized_user,
            open_chat_api_key="authorized-key",
            open_chat_user="authorized-user",
            open_chat_host=DEFAULT_HOST,
        )
        mock_delay.return_value = MagicMock(id="task-123")

        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(
            AUTOMATION_GENERATE_MESSAGE_REPLIES_URL,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.data["trigger"],
            "idempotent_actions__generate_message_replies",
        )
        self.assertEqual(response.data["task_id"], "task-123")
        mock_delay.assert_called_once_with(
            target_user_uuid=str(self.authorized_user.uuid),
            triggered_by_user_uuid=str(self.authorized_user.uuid),
        )

    def test_automation_generate_message_replies_requires_configuration(self):
        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.post(
            AUTOMATION_GENERATE_MESSAGE_REPLIES_URL,
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_idempotent_actions_lists_open_related_support_tasks(self):
        SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": "First pending message",
                "message_uuid": "message-1",
                "chat_uuid": "chat-1",
                "sender_user_id": self.view_only_user.pk,
                "recipient_user_id": self.authorized_user.pk,
            },
            parameters={"message": ""},
            created_by=self.authorized_user,
            related_user=self.view_only_user,
        )
        closed_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": "Already completed",
                "message_uuid": "message-2",
                "chat_uuid": "chat-2",
                "sender_user_id": self.view_only_user.pk,
                "recipient_user_id": self.authorized_user.pk,
            },
            parameters={"message": ""},
            created_by=self.authorized_user,
            related_user=self.view_only_user,
        )
        closed_task.status = SupportTask.Status.COMPLETED
        closed_task.save(update_fields=["status", "updated_at"])
        SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": "For another target user",
                "message_uuid": "message-3",
                "chat_uuid": "chat-3",
                "sender_user_id": self.authorized_user.pk,
                "recipient_user_id": self.view_only_user.pk,
            },
            parameters={"message": ""},
            created_by=self.authorized_user,
            related_user=self.authorized_user,
        )

        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.get(IDEMPOTENT_ACTIONS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["target_user_uuid"], str(self.authorized_user.uuid))
        self.assertEqual(len(response.data["results"]), 1)
        item = response.data["results"][0]
        self.assertEqual(item["idempotent_action"], "idempotent_actions__generate_message_replies")
        self.assertEqual(item["trigger_method"], "POST")
        self.assertEqual(item["support_task_relation"]["action_types"], ["support_reply"])
        self.assertEqual(item["support_task_relation"]["open_count"], 1)
        self.assertEqual(
            item["support_task_relation"]["suggested_filters"],
            {
                "status": ["NEW", "IN_PROGRESS"],
                "action_type": ["support_reply"],
            },
        )

    def test_idempotent_actions_manager_can_query_other_user(self):
        SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": "Manager targeted action",
                "message_uuid": "message-4",
                "chat_uuid": "chat-4",
                "sender_user_id": self.authorized_user.pk,
                "recipient_user_id": self.view_only_user.pk,
            },
            parameters={"message": ""},
            created_by=self.manager_user,
            related_user=self.authorized_user,
        )

        self.api_client.force_authenticate(user=self.manager_user)
        response = self.api_client.get(
            IDEMPOTENT_ACTIONS_URL,
            {"user_uuid": str(self.view_only_user.uuid)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["target_user_uuid"], str(self.view_only_user.uuid))
        self.assertEqual(response.data["results"][0]["support_task_relation"]["open_count"], 1)

    def test_automation_clear_message_replies_deletes_related_support_tasks(self):
        kept_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": "Other target user",
                "message_uuid": "other-message-uuid",
                "chat_uuid": "other-chat-uuid",
                "sender_user_id": self.authorized_user.pk,
                "recipient_user_id": self.view_only_user.pk,
            },
            parameters={"message": ""},
            created_by=self.authorized_user,
            related_user=self.authorized_user,
        )
        deleted_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": "Target user",
                "message_uuid": "target-message-uuid",
                "chat_uuid": "target-chat-uuid",
                "sender_user_id": self.view_only_user.pk,
                "recipient_user_id": self.authorized_user.pk,
            },
            parameters={"message": ""},
            created_by=self.authorized_user,
            related_user=self.view_only_user,
        )

        self.api_client.force_authenticate(user=self.authorized_user)
        response = self.api_client.delete(
            AUTOMATION_CLEAR_MESSAGE_REPLIES_URL,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["trigger"],
            "idempotent_actions__generate_message_replies.clear",
        )
        self.assertEqual(
            response.data["target_user_uuid"],
            str(self.authorized_user.uuid),
        )
        self.assertEqual(response.data["deleted_support_tasks_count"], 1)
        self.assertEqual(response.data["deleted_support_task_actions_count"], 1)
        self.assertFalse(SupportTask.objects.filter(pk=deleted_task.pk).exists())
        self.assertTrue(SupportTask.objects.filter(pk=kept_task.pk).exists())
