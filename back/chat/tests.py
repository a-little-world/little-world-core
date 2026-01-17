# Create your tests here.
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone as dj_timezone
from freezegun import freeze_time
from management.models.matches import Match
from management.random_test_users import create_test_user

from chat.models import Chat, Message


class TestFirstChatInteraction(TestCase):
    def setUp(self):
        from rest_framework.test import APIRequestFactory

        self.factory = APIRequestFactory()

        # Create two users
        self.user1 = create_test_user(40000, None, "Test123!", "first-chat-user1@test.de")
        self.user2 = create_test_user(40001, None, "Test123!", "first-chat-user2@test.de")

        # Create a match between the users
        self.match = Match.objects.create(user1=self.user1, user2=self.user2)

        # Create a chat between the users
        self.chat = Chat.get_or_create_chat(self.user1, self.user2)

    def _send_message_via_api(self, sender, text):
        """Helper to send a message via the API."""
        from rest_framework.test import force_authenticate

        from chat.api.messages import MessagesModelViewSet

        request = self.factory.post(
            f"/api/messages/{self.chat.uuid}/send/",
            {"text": text},
            format="json",
        )
        force_authenticate(request, user=sender)
        view = MessagesModelViewSet.as_view({"post": "send"})
        response = view(request, chat_uuid=str(self.chat.uuid))
        return response

    def test_first_chat_interaction_set_on_first_message(self):
        """Test that first_chat_interaction is set to current time when first message is sent."""
        # Ensure first_chat_interaction is None initially
        self.match.first_chat_interaction = None
        self.match.total_messages_counter = 0
        self.match.save()

        # Send first message via API
        first_message_time = dj_timezone.now()
        with freeze_time(first_message_time):
            response = self._send_message_via_api(self.user1, "First message")
            assert response.status_code == 200

        self.match.refresh_from_db()
        assert self.match.first_chat_interaction is not None
        assert self.match.first_chat_interaction == first_message_time

    def test_first_chat_interaction_not_overwritten_on_subsequent_messages(self):
        """Test that first_chat_interaction is not changed when additional messages are sent."""
        # Send first message via API to set first_chat_interaction
        response = self._send_message_via_api(self.user1, "First message")
        assert response.status_code == 200

        self.match.refresh_from_db()
        original_first_chat_interaction = self.match.first_chat_interaction
        assert original_first_chat_interaction is not None

        # Send additional messages via API
        response = self._send_message_via_api(self.user2, "Second message")
        assert response.status_code == 200

        response = self._send_message_via_api(self.user1, "Third message")
        assert response.status_code == 200

        self.match.refresh_from_db()
        # first_chat_interaction should remain unchanged
        assert self.match.first_chat_interaction == original_first_chat_interaction

    def test_first_chat_interaction_backfilled_from_existing_messages(self):
        """Test that first_chat_interaction is set to the first message's datetime when messages exist but first_chat_interaction is None."""
        # Create several messages with different timestamps (directly, not via API)
        first_message_time = dj_timezone.now() - timedelta(days=10)
        second_message_time = dj_timezone.now() - timedelta(days=8)
        third_message_time = dj_timezone.now() - timedelta(days=5)

        with freeze_time(first_message_time):
            Message.objects.create(
                chat=self.chat,
                sender=self.user1,
                recipient=self.user2,
                text="First message",
            )

        with freeze_time(second_message_time):
            Message.objects.create(
                chat=self.chat,
                sender=self.user2,
                recipient=self.user1,
                text="Second message",
            )

        with freeze_time(third_message_time):
            Message.objects.create(
                chat=self.chat,
                sender=self.user1,
                recipient=self.user2,
                text="Third message",
            )

        # Set match state as if first_chat_interaction was never set (simulating legacy data)
        self.match.first_chat_interaction = None
        self.match.total_messages_counter = 3
        self.match.save()

        # Now send a new message via API which should trigger the backfill logic
        response = self._send_message_via_api(self.user2, "Fourth message")
        assert response.status_code == 200

        self.match.refresh_from_db()
        # first_chat_interaction should be set to the first message's created time
        assert self.match.first_chat_interaction == first_message_time
