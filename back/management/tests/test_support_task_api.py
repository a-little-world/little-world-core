from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from management.actions.registry import registered_action_types, registered_task_types
from management.models.object_history import ObjectHistory
from management.models.support_task import SupportTask
from management.models.user import User
from management.permissions import ManagementPermission


class SupportTaskApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        content_type = ContentType.objects.get(app_label="management", model="state")
        cls.matching_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.MATCHING_USER.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.MATCHING_USER.codename},
        )
        cls.reply_permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES.codename},
        )
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

        cls.direct_matching_user = User.objects.create_user(
            email="direct-matching-support-task@example.com",
            password="Test123!",
            first_name="Direct",
            last_name="Matching",
        )
        cls.direct_matching_user.user_permissions.add(cls.matching_permission)

        cls.group_matching_user = User.objects.create_user(
            email="group-matching-support-task@example.com",
            password="Test123!",
            first_name="Group",
            last_name="Matching",
        )
        matching_group = Group.objects.create(name="support-task-matching")
        matching_group.permissions.add(cls.matching_permission)
        cls.group_matching_user.groups.add(matching_group)

        cls.superuser = User.objects.create_user(
            email="super-support-task@example.com",
            password="Test123!",
            first_name="Super",
            last_name="User",
        )
        cls.superuser.is_staff = True
        cls.superuser.is_superuser = True
        cls.superuser.save(update_fields=["is_staff", "is_superuser"])

        cls.inactive_matching_user = User.objects.create_user(
            email="inactive-matching-support-task@example.com",
            password="Test123!",
            first_name="Inactive",
            last_name="Matching",
        )
        cls.inactive_matching_user.user_permissions.add(cls.matching_permission)
        cls.inactive_matching_user.is_active = False
        cls.inactive_matching_user.save(update_fields=["is_active"])

        cls.direct_reply_user = User.objects.create_user(
            email="direct-reply-support-task@example.com",
            password="Test123!",
            first_name="Direct",
            last_name="Reply",
        )
        cls.direct_reply_user.user_permissions.add(cls.reply_permission)
        cls.group_reply_user = User.objects.create_user(
            email="group-reply-support-task@example.com",
            password="Test123!",
            first_name="Group",
            last_name="Reply",
        )
        reply_group = Group.objects.create(name="support-task-reply")
        reply_group.permissions.add(cls.reply_permission)
        cls.group_reply_user.groups.add(reply_group)

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

    def test_support_reply_defaults_to_unassigned(self):
        task = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.regular_user,
            static_parameters={"kind_display": "General", "message_preview": "A"},
            parameters={"message": ""},
        )

        self.assertFalse(task.assignees.exists())

    def test_update_replaces_and_serializes_multiple_assignees(self):
        task = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.regular_user,
            static_parameters={"kind_display": "General", "message_preview": "A"},
            parameters={"message": ""},
        )

        response = self._client_for(self.admin_user).patch(
            f"/api/support_task/{task.id}/update/",
            {"assignee_ids": [self.direct_matching_user.id, self.group_matching_user.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {profile["id"] for profile in response.json()["assignee_profiles"]},
            {self.direct_matching_user.id, self.group_matching_user.id},
        )
        self.assertEqual(
            set(task.assignees.values_list("id", flat=True)),
            {self.direct_matching_user.id, self.group_matching_user.id},
        )
        history = ObjectHistory.objects.filter(
            object_id=task.id,
            content_type__app_label="management",
            content_type__model="supporttask",
            field="assignees",
        ).latest("id")
        self.assertEqual(history.new_value, sorted([self.direct_matching_user.id, self.group_matching_user.id]))

    def test_list_filters_by_assignee_and_unassigned(self):
        assigned_task = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.regular_user,
            static_parameters={"kind_display": "General", "message_preview": "Assigned"},
            parameters={"message": ""},
        )
        assigned_task.set_assignees([self.direct_matching_user])
        unassigned_task = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.regular_user,
            static_parameters={"kind_display": "General", "message_preview": "Unassigned"},
            parameters={"message": ""},
        )
        unassigned_task.set_assignees([])

        assigned_response = self._client_for(self.admin_user).get(
            f"/api/support_task/?assigned_to={self.direct_matching_user.id}"
        )
        unassigned_response = self._client_for(self.admin_user).get("/api/support_task/?assigned_to=unassigned")

        self.assertEqual([row["id"] for row in assigned_response.json()["results"]], [assigned_task.id])
        self.assertEqual([row["id"] for row in unassigned_response.json()["results"]], [unassigned_task.id])

    def test_assignee_users_lists_active_support_users(self):
        response = self._client_for(self.admin_user).get("/api/support_task/assignee_users/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row["id"] for row in response.json()},
            {
                self.admin_user.id,
                self.superuser.id,
                self.direct_matching_user.id,
                self.group_matching_user.id,
                self.direct_reply_user.id,
                self.group_reply_user.id,
            },
        )

    def test_manual_create_accepts_multiple_assignees(self):
        response = self._client_for(self.admin_user).post(
            "/api/support_task/create_manual/",
            {
                "title": "Manual",
                "description": "",
                "priority": "MEDIUM",
                "assignee_ids": [self.direct_matching_user.id, self.group_matching_user.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        task = SupportTask.objects.get(pk=response.json()["id"])
        self.assertEqual(
            set(task.assignees.values_list("id", flat=True)),
            {self.direct_matching_user.id, self.group_matching_user.id},
        )

    def test_support_only_user_can_access_tasks_and_notes(self):
        task = SupportTask.create_of_type(
            "support_reply",
            created_by=self.admin_user,
            related_user=self.regular_user,
            static_parameters={"kind_display": "General", "message_preview": "A"},
            parameters={"message": ""},
        )
        client = self._client_for(self.direct_reply_user)

        list_response = client.get("/api/support_task/")
        detail_response = client.get(f"/api/support_task/{task.id}/")
        note_response = client.post(f"/api/support_task/{task.id}/notes/", {"text": "Looks good"}, format="json")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(note_response.status_code, 201)
        task.refresh_from_db()
        self.assertEqual(set(task.assignees.values_list("id", flat=True)), {self.direct_reply_user.id})

    def test_manual_task_can_be_executed(self):
        create_response = self._client_for(self.admin_user).post(
            "/api/support_task/create_manual/",
            {"title": "Manual TODO", "assignee_ids": [self.direct_matching_user.id]},
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        task_id = create_response.json()["id"]

        response = self._client_for(self.admin_user).post(f"/api/support_task/{task_id}/action/execute/", format="json")

        self.assertEqual(response.status_code, 200)
        task = SupportTask.objects.get(pk=task_id)
        self.assertEqual(task.action.status, task.action.Status.EXECUTED)
        self.assertEqual(task.status, task.Status.COMPLETED)

    def test_manual_task_bulk_complete(self):
        create_response = self._client_for(self.admin_user).post(
            "/api/support_task/create_manual/",
            {"title": "Manual TODO"},
            format="json",
        )
        task_id = create_response.json()["id"]

        response = self._client_for(self.admin_user).post(
            "/api/support_task/bulk/",
            {"task_ids": [task_id], "action": "complete"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"succeeded": [task_id], "failed": []})
        task = SupportTask.objects.get(pk=task_id)
        self.assertEqual(task.action.status, task.action.Status.EXECUTED)
        self.assertEqual(task.status, task.Status.COMPLETED)

    def test_manual_create_rejects_unknown_related_user(self):
        response = self._client_for(self.admin_user).post(
            "/api/support_task/create_manual/",
            {"title": "Manual TODO", "related_user_id": 999999},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

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
                    "manual",
                }
            ),
        )
