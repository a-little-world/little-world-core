from django.test import TestCase
from rest_framework.test import APIClient

from management.actions.registry import registered_action_types, registered_task_types
from management.models.support_task import SupportTask
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

    def test_list_filters_by_related_user(self):
        task_for_regular_user = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.regular_user,
            static_parameters={"kind_display": "General", "message_preview": "A"},
            parameters={"message": ""},
        )
        _task_for_admin_user = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.admin_user,
            static_parameters={"kind_display": "General", "message_preview": "B"},
            parameters={"message": ""},
        )

        response = self._client_for(self.admin_user).get(f"/api/support_task/?related_user={self.regular_user.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], task_for_regular_user.id)

    def test_bulk_delete_support_tasks(self):
        task = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.regular_user,
            static_parameters={"kind_display": "General", "message_preview": "A"},
            parameters={"message": ""},
        )

        response = self._client_for(self.admin_user).post(
            "/api/support_task/bulk/",
            {"task_ids": [task.id], "action": "delete"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"succeeded": [task.id], "failed": []})
        self.assertFalse(SupportTask.objects.filter(pk=task.id).exists())

    def test_bulk_cancel_open_support_task(self):
        task = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.regular_user,
            static_parameters={"kind_display": "General", "message_preview": "A"},
            parameters={"message": ""},
        )

        response = self._client_for(self.admin_user).post(
            "/api/support_task/bulk/",
            {"task_ids": [task.id], "action": "cancel"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"succeeded": [task.id], "failed": []})
        task.refresh_from_db()
        self.assertEqual(task.status, SupportTask.Status.COMPLETED)
        self.assertEqual(task.action.status, task.action.Status.CANCELLED)


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
