from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from emails.models import EmailLog
from rest_framework.test import APIClient

from management.models.matches import Match
from management.models.user import User
from management.permissions import ManagementPermission


class UserAdvancedMigrationApiTests(TestCase):
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

        cls.matching_user = User.objects.create_user(
            email="migration-matcher@test.de",
            username="migration-matcher@test.de",
            password="Test123!",
            first_name="Matcher",
            last_name="User",
        )
        cls.matching_user.user_permissions.add(cls.matching_perm, cls.apply_perm)

        cls.apply_only_user = User.objects.create_user(
            email="migration-apply-only@test.de",
            username="migration-apply-only@test.de",
            password="Test123!",
            first_name="Apply",
            last_name="Only",
        )
        cls.apply_only_user.user_permissions.add(cls.apply_perm)

        cls.regular_user = User.objects.create_user(
            email="migration-regular@test.de",
            username="migration-regular@test.de",
            password="Test123!",
            first_name="Regular",
            last_name="User",
        )

        cls.staff_target = User.objects.create_user(
            email="migration-staff-target@test.de",
            username="migration-staff-target@test.de",
            password="Test123!",
            first_name="Staff",
            last_name="Target",
        )
        cls.staff_target.is_staff = True
        cls.staff_target.save(update_fields=["is_staff"])

    def setUp(self):
        self.target = User.objects.create_user(
            email="migration-target@test.de",
            username="migration-target@test.de",
            password="Test123!",
            first_name="Target",
            last_name="User",
        )
        self.target.state.company = "lingoda"
        self.target.state.save()
        self.matching_user.grant_management_access(self.target, granted_by=self.matching_user)

    def _auth(self, user=None):
        self.api_client.force_authenticate(user=user or self.matching_user)

    def test_change_email_updates_email_username_and_archives_old(self):
        self._auth()
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/change_email/",
            {"email": "migration-target-new@test.de", "send_verification_email": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "migration-target-new@test.de")
        self.assertEqual(self.target.username, "migration-target-new@test.de")
        self.assertIn("migration-target@test.de", self.target.state.past_emails)
        self.assertFalse(
            EmailLog.objects.filter(receiver=self.target, template="automatic-emails-u001").exists(),
            "no verification mail should be sent when send_verification_email is false",
        )

    def test_change_email_sends_verification_when_requested(self):
        self._auth()
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/change_email/",
            {"email": "migration-target-new@test.de", "send_verification_email": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(EmailLog.objects.filter(receiver=self.target, template="automatic-emails-u001").exists())

    def test_change_email_rejects_duplicate(self):
        self._auth()
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/change_email/",
            {"email": self.matching_user.email},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "migration-target@test.de")

    def test_change_email_blocks_staff_target(self):
        self.matching_user.grant_management_access(self.staff_target, granted_by=self.matching_user)
        self._auth()
        response = self.api_client.post(
            f"/api/matching/users/{self.staff_target.id}/change_email/",
            {"email": "migration-staff-target-new@test.de"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.staff_target.refresh_from_db()
        self.assertEqual(self.staff_target.email, "migration-staff-target@test.de")

    def test_change_email_requires_matching_permission(self):
        self.apply_only_user.grant_management_access(self.target, granted_by=self.apply_only_user)
        self._auth(self.apply_only_user)
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/change_email/",
            {"email": "migration-target-new@test.de"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_set_company_updates_and_archives_previous(self):
        self._auth()
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/set_company/",
            {"company": "newco"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.target.state.refresh_from_db()
        self.assertEqual(self.target.state.company, "newco")
        self.assertIn("lingoda", self.target.state.past_companies)

        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/set_company/",
            {"company": None},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.target.state.refresh_from_db()
        self.assertIsNone(self.target.state.company)
        self.assertIn("newco", self.target.state.past_companies)

    def test_set_company_requires_access(self):
        self._auth(self.regular_user)
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/set_company/",
            {"company": "newco"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_migrate_user_censors_in_place_and_keeps_match(self):
        partner = User.objects.create_user(
            email="migration-partner@test.de",
            username="migration-partner@test.de",
            password="Test123!",
            first_name="Partner",
            last_name="User",
        )
        match = Match.objects.create(user1=self.target, user2=partner, support_matching=False)

        self._auth()
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/migrate_user/",
            {"remove_company": True, "censor": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        migrated = User.objects.get(pk=self.target.pk)
        self.assertFalse(migrated.is_active)
        self.assertTrue(migrated.email.startswith("deleted_"))
        self.assertEqual(migrated.profile.first_name, "Ghost")
        self.assertIsNotNone(migrated.state.deleted_at)
        self.assertIsNotNone(migrated.state.migrated_at)
        self.assertEqual(migrated.state.migrated_from_company, "lingoda")
        self.assertIsNone(migrated.state.company)
        self.assertIn("lingoda", migrated.state.past_companies)

        still_resolves = Match.objects.get(pk=match.pk)
        self.assertEqual(still_resolves.user1_id, self.target.pk)

    def test_migrate_user_can_change_email_without_censoring(self):
        self._auth()
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/migrate_user/",
            {"new_email": "migration-target-new@test.de", "censor": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertEqual(self.target.email, "migration-target-new@test.de")
        self.assertEqual(self.target.state.company, "lingoda")
        self.assertIsNone(self.target.state.deleted_at)
        self.assertIsNotNone(self.target.state.migrated_at)

    def test_migrate_user_requires_apply_permission(self):
        self.matching_user.user_permissions.remove(self.apply_perm)
        self._auth()
        response = self.api_client.post(
            f"/api/matching/users/{self.target.id}/migrate_user/",
            {"censor": True},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
