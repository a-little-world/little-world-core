from chat.models import Chat, Message
from django.test import TestCase
from rest_framework.test import APIClient

from management.controller import get_base_management_user
from management.models.user import User


class AdvancedUserDeleteMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            email="delete-msg-staff@test.de",
            username="delete-msg-staff@test.de",
            password="Test123!",
            first_name="Delete",
            last_name="Staff",
        )
        cls.staff_user.is_staff = True
        cls.staff_user.save(update_fields=["is_staff"])

        cls.target_user = User.objects.create_user(
            email="delete-msg-target@test.de",
            username="delete-msg-target@test.de",
            password="Test123!",
            first_name="Delete",
            last_name="Target",
        )

        cls.base_management_user = get_base_management_user()
        cls.chat = Chat.get_or_create_chat(cls.base_management_user, cls.target_user)

    def _post_delete(self, message_uuid):
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        return client.post(
            f"/api/matching/users/{self.target_user.pk}/delete_message/",
            {"message_id": str(message_uuid)},
            format="json",
        )

    def test_delete_unread_message_succeeds(self):
        message = Message.objects.create(
            chat=self.chat,
            sender=self.base_management_user,
            recipient=self.target_user,
            text="Unread support message",
            read=False,
        )

        response = self._post_delete(message.uuid)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Message.objects.filter(pk=message.pk).exists())

    def test_delete_read_message_is_rejected(self):
        message = Message.objects.create(
            chat=self.chat,
            sender=self.base_management_user,
            recipient=self.target_user,
            text="Read support message",
            read=True,
        )

        response = self._post_delete(message.uuid)

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())
