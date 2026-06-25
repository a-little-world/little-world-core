from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from management.controller import get_base_management_user
from management.models.user import User
from management.permissions import ManagementPermission
from management.tasks import sync_full_user_access_for_manager


class ReceivesFullUserAccessTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        content_type = ContentType.objects.get(app_label="management", model="state")
        cls.receives_full_access_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.RECEIVES_FULL_USER_ACCESS.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.RECEIVES_FULL_USER_ACCESS.codename},
        )

    @patch("management.tasks.sync_full_user_access_for_manager.delay")
    def test_grant_permission_enqueues_full_access_sync_task(self, mock_delay):
        manager = User.objects.create_user(
            email="receives-full-access-manager@test.de",
            username="receives-full-access-manager@test.de",
            password="Test123!",
            first_name="Receives",
            last_name="Access",
        )

        success = manager.grant_permission(ManagementPermission.RECEIVES_FULL_USER_ACCESS)

        self.assertTrue(success)
        mock_delay.assert_called_once_with(manager.pk)

    def test_sync_task_grants_manager_access_to_all_base_management_managed_users(self):
        base_management_user = get_base_management_user()
        manager = User.objects.create_user(
            email="sync-target-manager@test.de",
            username="sync-target-manager@test.de",
            password="Test123!",
            first_name="Sync",
            last_name="Target",
        )
        manager.user_permissions.add(self.receives_full_access_permission)

        user_a = User.objects.create_user(
            email="sync-user-a@test.de",
            username="sync-user-a@test.de",
            password="Test123!",
            first_name="Sync",
            last_name="UserA",
        )
        user_b = User.objects.create_user(
            email="sync-user-b@test.de",
            username="sync-user-b@test.de",
            password="Test123!",
            first_name="Sync",
            last_name="UserB",
        )

        base_management_user.grant_management_access(user_a, granted_by=base_management_user)
        base_management_user.grant_management_access(user_b, granted_by=base_management_user)

        self.assertFalse(manager.has_management_access(user_a))
        self.assertFalse(manager.has_management_access(user_b))

        result = sync_full_user_access_for_manager(manager.pk)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(manager.has_management_access(user_a))
        self.assertTrue(manager.has_management_access(user_b))
