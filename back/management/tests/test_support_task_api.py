from django.test import TestCase
from rest_framework.test import APIClient

from management.actions.registry import registered_action_types, registered_task_types
from management.models.user import User


class SupportTaskApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.regular_user = User.objects.create_user(
            email="regular-support-task@example.com",
            password="Test123!",
            first_name="Regular",
            last_name="User",
        )
        cls.admin_user = User.objects.create_user(
            email="admin-support-task@example.com",
            password="Test123!",
            first_name="Admin",
            last_name="User",
        )
        cls.admin_user.is_staff = True
        cls.admin_user.save(update_fields=["is_staff"])

    def _client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def test_list_requires_matching_panel_permission(self):
        response = self._client_for(self.regular_user).get("/api/support_task/")

        self.assertEqual(response.status_code, 403)

    def test_list_allows_missing_status_filter(self):
        response = self._client_for(self.admin_user).get("/api/support_task/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "count": 0,
                "page": 1,
                "next": None,
                "previous": None,
                "results": [],
                "page_size": 20,
                "pages_total": 1,
                "next_page": None,
                "results_total": 0,
                "previous_page": None,
                "last_page": 1,
                "items_total": 0,
                "first_page": 1,
            },
        )


class SupportTaskRegistryTests(TestCase):
    def test_only_initial_action_set_is_registered(self):
        self.assertEqual(
            registered_task_types(),
            frozenset({"support_reply", "change_user_type", "change_country_of_residence"}),
        )
        self.assertEqual(
            registered_action_types(),
            frozenset(
                {
                    "support_reply",
                    "message_action_change_user_type",
                    "profile_change_action_country_of_residence",
                }
            ),
        )
