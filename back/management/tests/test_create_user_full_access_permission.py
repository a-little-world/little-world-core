from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from management.controller import create_user
from management.models.user import User
from management.permissions import ManagementPermission


class CreateUserFullAccessPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        content_type = ContentType.objects.get(app_label="management", model="state")
        full_access_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.RECEIVES_FULL_USER_ACCESS.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.RECEIVES_FULL_USER_ACCESS.codename},
        )

        cls.full_access_manager = User.objects.create_user(
            email="full-access-manager@test.de",
            username="full-access-manager@test.de",
            password="Test123!",
            first_name="Full",
            last_name="Access",
        )
        cls.full_access_manager.user_permissions.add(full_access_permission)

    def test_create_user_auto_grants_access_to_full_access_permission_users(self):
        created_user = create_user(
            email="created-auto-grant@test.de",
            password="Test123!",
            first_name="Created",
            second_name="AutoGrant",
            birth_year=1990,
            send_verification_mail=False,
            auto_apply_user_access_permission=True,
        )

        self.assertTrue(self.full_access_manager.has_management_access(created_user))

    def test_create_user_can_disable_auto_grant_full_access_permission(self):
        created_user = create_user(
            email="created-no-auto-grant@test.de",
            password="Test123!",
            first_name="Created",
            second_name="NoAutoGrant",
            birth_year=1991,
            send_verification_mail=False,
            auto_apply_user_access_permission=False,
        )

        self.assertFalse(self.full_access_manager.has_management_access(created_user))
