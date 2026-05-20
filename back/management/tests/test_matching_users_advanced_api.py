from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from management.models.user import User
from management.permissions import ManagementPermission


class MatchingUsersAdvancedApiTests(TestCase):
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

        cls.matching_perm = ensure_permission(ManagementPermission.MATCHING_USER.codename)
        cls.apply_perm = ensure_permission(ManagementPermission.APPLY_MANAGEMENT_PERMISSIONS.codename)

        cls.staff_user = User.objects.create_user(
            email="staff-matching-users@test.de",
            username="staff-matching-users@test.de",
            password="Test123!",
            first_name="Staff",
            last_name="User",
        )
        cls.staff_user.is_staff = True
        cls.staff_user.save(update_fields=["is_staff"])
        cls.regular_user = User.objects.create_user(
            email="regular-matching-users@test.de",
            username="regular-matching-users@test.de",
            password="Test123!",
            first_name="Regular",
            last_name="User",
        )
        cls.permission_admin = User.objects.create_user(
            email="perm-admin-matching-users@test.de",
            username="perm-admin-matching-users@test.de",
            password="Test123!",
            first_name="Perm",
            last_name="Admin",
        )
        cls.permission_admin.user_permissions.add(cls.apply_perm)

        cls.matching_user_a = User.objects.create_user(
            email="matcher-a@test.de",
            username="matcher-a@test.de",
            password="Test123!",
            first_name="Matcher",
            last_name="A",
        )
        cls.matching_user_a.user_permissions.add(cls.matching_perm, cls.apply_perm)

        cls.matching_user_b = User.objects.create_user(
            email="matcher-b@test.de",
            username="matcher-b@test.de",
            password="Test123!",
            first_name="Matcher",
            last_name="B",
        )
        cls.matching_user_b.user_permissions.add(cls.matching_perm)

        cls.non_matching_user = User.objects.create_user(
            email="not-matcher@test.de",
            username="not-matcher@test.de",
            password="Test123!",
            first_name="Not",
            last_name="Matcher",
        )

    def test_list_requires_matching_user_or_staff(self):
        self.api_client.force_authenticate(user=self.regular_user)
        response = self.api_client.get("/api/matching/matching_users/")
        self.assertEqual(response.status_code, 403)

        self.api_client.force_authenticate(user=self.permission_admin)
        response = self.api_client.get("/api/matching/matching_users/")
        self.assertEqual(response.status_code, 403)

    def test_list_allowed_for_matching_user_without_apply_permission(self):
        self.api_client.force_authenticate(user=self.matching_user_b)
        response = self.api_client.get("/api/matching/matching_users/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["can_edit_management_permissions"])

    def test_list_returns_only_matching_users_for_staff(self):
        self.api_client.force_authenticate(user=self.staff_user)
        response = self.api_client.get("/api/matching/matching_users/")
        self.assertEqual(response.status_code, 200)

        result_ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(result_ids, {self.matching_user_a.id, self.matching_user_b.id})
        self.assertNotIn(self.non_matching_user.id, result_ids)

    def test_list_includes_management_permissions(self):
        self.api_client.force_authenticate(user=self.matching_user_a)
        response = self.api_client.get("/api/matching/matching_users/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_edit_management_permissions"])

        matcher_a = next(row for row in response.data["results"] if row["id"] == self.matching_user_a.id)
        enabled_codenames = {perm["codename"] for perm in matcher_a["permissions"] if perm["enabled"]}
        self.assertIn(ManagementPermission.MATCHING_USER.codename, enabled_codenames)
        self.assertIn(ManagementPermission.APPLY_MANAGEMENT_PERMISSIONS.codename, enabled_codenames)
