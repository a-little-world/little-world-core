import json
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from management.models.user import User
from management.tests.helpers import register_user
from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching


class RandomCallsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        
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
        self.lobby = RandomCallLobby.objects.create(
            name="default",
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=1)
        )

    def test_setup(self):
        """Verify that users and lobby are created correctly."""
        self.assertTrue(User.objects.filter(pk=self.user1.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.user2.pk).exists())
        self.assertEqual(RandomCallLobby.objects.count(), 1)
        self.assertEqual(self.lobby.name, "default")
