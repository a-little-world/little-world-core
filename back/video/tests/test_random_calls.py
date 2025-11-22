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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_prevent_duplicate_matching(self):
        """
        Test that users who are already matched are not matched again.
        """
        # Create a 3rd user
        user3 = register_user({
            "email": "user3@example.com",
            "password1": "Test123!",
            "password2": "Test123!",
            "first_name": "User",
            "second_name": "Three",
            "birth_year": 1995
        })

        # Join all users to lobby
        for u in [self.user1, self.user2, user3]:
            self.client.force_authenticate(user=u)
            self.client.post("/api/random_calls/lobby/default/join")

        # Check matchings
        matchings = RandomCallMatching.objects.filter(lobby=self.lobby)
        self.assertEqual(matchings.count(), 1)
        
        # Identify who is matched
        matched_users = [matchings.first().u1, matchings.first().u2]
        unmatched_user = user3
        if user3 in matched_users:
            unmatched_user = self.user1 if self.user1 not in matched_users else self.user2
            
        # Ensure unmatched user is really unmatched
        self.assertNotIn(unmatched_user, matched_users)

        # Trigger matching again (by having the unmatched user join again or just waiting/triggering task)
        # In our implementation, joining triggers the task.
        # But since we are eager, the task already ran for each join.
        # Let's try to manually trigger the task again to see if it picks up the already matched users
        from video.tasks import random_call_lobby_perform_matching
        random_call_lobby_perform_matching("default")
        
        # Should still be only 1 matching because we only have 1 unmatched user left
        # If the logic is broken, it might match the unmatched user with one of the already matched users
        self.assertEqual(RandomCallMatching.objects.count(), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_exit_and_rejoin_lobby(self):
        """
        Test that users can exit the lobby and rejoin without getting already_joined=True.
        """
        # User 1 joins
        self.client.force_authenticate(user=self.user1)
        response = self.client.post("/api/random_calls/lobby/default/join")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["already_joined"])
        
        # Verify user is in lobby and active
        lobby_user = RandomCallLobbyUser.objects.filter(user=self.user1, lobby=self.lobby).first()
        self.assertIsNotNone(lobby_user)
        self.assertTrue(lobby_user.is_active)
        
        # User 1 exits
        response = self.client.post("/api/random_calls/lobby/default/exit")
        self.assertEqual(response.status_code, 200)
        
        # Verify user is marked as inactive
        lobby_user.refresh_from_db()
        self.assertFalse(lobby_user.is_active)
        
        # User 1 rejoins - should not say already_joined
        response = self.client.post("/api/random_calls/lobby/default/join")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["already_joined"], "User should not be marked as already_joined after exiting")
        
        # Verify user is reactivated
        lobby_user.refresh_from_db()
        self.assertTrue(lobby_user.is_active)

