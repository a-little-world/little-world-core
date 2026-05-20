from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from management.api.matching_panel_user import get_matching_panel_user_data
from management.models.user import User
from management.permissions import ManagementPermission


class MatchingPanelUserApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.api_client = APIClient()
        content_type = ContentType.objects.get(app_label="management", model="state")

        cls.matching_perm = Permission.objects.get_or_create(
            codename=ManagementPermission.MATCHING_USER.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.MATCHING_USER.codename},
        )[0]

        cls.matcher = User.objects.create_user(
            email="panel-matcher@test.de",
            username="panel-matcher@test.de",
            password="Test123!",
            first_name="Panel",
            last_name="Matcher",
        )
        cls.matcher.user_permissions.add(cls.matching_perm)

    def test_matching_panel_me_returns_panel_user_shape(self):
        self.api_client.force_authenticate(user=self.matcher)
        response = self.api_client.get("/api/matching/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["first_name"], self.matcher.profile.first_name)
        self.assertEqual(response.data["last_name"], self.matcher.profile.second_name)
        self.assertTrue(response.data["is_matching_user"])
        self.assertIn("permissions", response.data)

    def test_get_matching_panel_user_data_matches_serializer(self):
        data = get_matching_panel_user_data(self.matcher)
        self.assertEqual(data["email"], self.matcher.email)
        self.assertEqual(len(data["permissions"]), len(ManagementPermission))
