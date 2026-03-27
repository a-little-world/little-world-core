from django.test import TestCase
from management.controller import create_user
from rest_framework.test import APIClient

from emails.models import DynamicTemplate


class DynamicTemplateApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.matching_user = create_user(
            email="matching-user@example.com",
            password="Test123!",
            first_name="Matching",
            second_name="User",
            birth_year=1989,
            send_verification_mail=False,
        )
        self.matching_user.state.extra_user_permission = [
            self.matching_user.state.ExtraUserPermissionChoices.MATCHING_USER
        ]
        self.matching_user.state.save()
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
