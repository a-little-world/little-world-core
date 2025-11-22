import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from management.models.user import User
from management.tests.helpers import register_user
from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching


from back.celery import app

class RandomCallsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        app.conf.task_always_eager = True
        
        # Create users
        self.user1 = register_user({
            "email": "user1@example.com",
            "password1": "Test123!",
            "password2": "Test123!",
            "first_name": "User",
            "second_name": "One",
            "birth_year": 1990
        })
        self.user2 = register_user({
            "email": "user2@example.com",
            "password1": "Test123!",
            "password2": "Test123!",
            "first_name": "User",
            "second_name": "Two",
            "birth_year": 1992
        })
        
        # Create default lobby
        self.lobby, _ = RandomCallLobby.objects.get_or_create(
            name="default",
            defaults={
                "start_time": timezone.now() - timezone.timedelta(hours=1),
                "end_time": timezone.now() + timezone.timedelta(hours=1)
            }
        )

    def test_setup(self):
        """Verify that users and lobby are created correctly."""
        self.assertTrue(User.objects.filter(pk=self.user1.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.user2.pk).exists())
        self.assertEqual(RandomCallLobby.objects.count(), 1)
        self.assertEqual(self.lobby.name, "default")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_join_lobby_and_matching_trigger(self):
        """
        Test that both users can join the lobby and the matching task is triggered and executed.
        """
        # User 1 joins
        self.client.force_authenticate(user=self.user1)
        response = self.client.post("/api/random_calls/lobby/default/join")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lobby"], self.lobby.uuid)
        self.assertFalse(response.data["already_joined"])
        
        # User 2 joins
        self.client.force_authenticate(user=self.user2)
        response = self.client.post("/api/random_calls/lobby/default/join")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["already_joined"])
        
        # User 1 checks status
        self.client.force_authenticate(user=self.user1)
        response = self.client.get("/api/random_calls/lobby/default/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lobby"], self.lobby.uuid)
        
        # The task should have run synchronously and created the matching
        self.assertEqual(RandomCallMatching.objects.count(), 1, "Matching was not created in DB")
        
        self.assertIsNotNone(response.data["matching"])
        self.assertFalse(response.data["matching"]["accepted"])
