from django.contrib.auth.models import Permission
from django.test import TestCase
from management.models.user import User
from management.permissions import ManagementPermission
from rest_framework.test import APIClient

from emails.models import DynamicTemplate


class DynamicTemplateApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.matching_user = User.objects.create_user(
            email="matching-user@example.com",
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
            self.matching_user.user_permissions.add(permission)
        self.client.force_authenticate(user=self.matching_user)

    def test_retrieve_returns_404_for_unknown_template(self):
        response = self.client.get("/api/matching/emails/dynamic_templates/does-not-exist/")

        self.assertEqual(response.status_code, 404)
        self.assertIn("does not exist", str(response.data["detail"]))

    def test_retrieve_resolves_spacing_variants(self):
        template = DynamicTemplate.objects.create(
            template_name="Mon - Gruppengespräche dieser Woche",
            template="<p>Hello</p>",
            subject="Weekly talks",
            content={"foo": "bar"},
            category_id="dynamic",
            sender_id="noreply",
        )

        response = self.client.get(
            "/api/matching/emails/dynamic_templates/Mon%20%20-%20Gruppengespr%C3%A4che%20dieser%20Woche/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], template.id)
        self.assertEqual(response.data["template_name"], template.template_name)
