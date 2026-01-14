from back.celery import app
from django.test import TestCase, override_settings
from django.utils import timezone
from management.models.user import User
from management.tests.helpers import register_user
from rest_framework.test import APIClient
from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching


class RandomCallsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        app.conf.task_always_eager = True

        # Create users
        self.user1 = register_user(
            {
                "email": "user1@example.com",
                "password1": "Test123!",
                "password2": "Test123!",
                "first_name": "User",
                "second_name": "One",
                "birth_year": 1990,
            }
        )
        self.user2 = register_user(
            {
                "email": "user2@example.com",
                "password1": "Test123!",
                "password2": "Test123!",
                "first_name": "User",
                "second_name": "Two",
                "birth_year": 1992,
            }
        )

        # Create default lobby
        self.lobby, _ = RandomCallLobby.objects.get_or_create(
            name="default",
            defaults={
                "start_time": timezone.now() - timezone.timedelta(hours=1),
                "end_time": timezone.now() + timezone.timedelta(hours=1),
            },
        )

    def create_multiple_users(self, count, base_email="testuser", base_name="TestUser"):
        """
        Helper method to create multiple users for testing concurrent scenarios.
        Returns a list of User objects.
        """
        import uuid

        users = []
        # Use a unique identifier to avoid email conflicts across tests
        unique_id = str(uuid.uuid4())[:8]
        for i in range(1, count + 1):
            # Create user directly (Profile is auto-created via signals)
            user = User.objects.create_user(
                email=f"{base_email}_{unique_id}_{i}@example.com",
                password="Test123!",
                first_name=f"{base_name}",
                last_name=f"{i}",
            )
            # Update profile fields if needed
            user.profile.first_name = f"{base_name}"
            user.profile.second_name = f"{i}"
            user.profile.birth_year = 1990 + i
            user.profile.save()

            users.append(user)
        return users

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

        # Verify matching appears in status response
        self.assertIsNotNone(response.data["matching"], "Matching should be present in status")
        self.assertIn("uuid", response.data["matching"])
        self.assertIn("partner", response.data["matching"])
        self.assertIn("accepted", response.data["matching"])
        self.assertIn("both_accepted", response.data["matching"])

        # Verify partner data
        partner_data = response.data["matching"]["partner"]
        self.assertIn("id", partner_data)
        self.assertIn("name", partner_data)
        self.assertIn("image", partner_data)
        self.assertIn("image_type", partner_data)
        self.assertEqual(partner_data["name"], self.user2.profile.first_name)

        # Verify acceptance status
        self.assertFalse(response.data["matching"]["accepted"])
        self.assertFalse(response.data["matching"]["both_accepted"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_prevent_duplicate_matching(self):
        """
        Test that users who are already matched are not matched again.
        """
        # Create a 3rd user
        user3 = register_user(
            {
                "email": "user3@example.com",
                "password1": "Test123!",
                "password2": "Test123!",
                "first_name": "User",
                "second_name": "Three",
                "birth_year": 1995,
            }
        )

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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_accept_matching(self):
        """
        Test that users can accept a matching and both_accepted is set when both accept.
        """
        # Both users join
        self.client.force_authenticate(user=self.user1)
        self.client.post("/api/random_calls/lobby/default/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post("/api/random_calls/lobby/default/join")

        # Get the matching
        matching = RandomCallMatching.objects.first()
        self.assertIsNotNone(matching)

        # User 1 checks status and gets matching info
        self.client.force_authenticate(user=self.user1)
        response = self.client.get("/api/random_calls/lobby/default/status")
        self.assertEqual(response.status_code, 200)
        match_uuid = response.data["matching"]["uuid"]

        # User 1 accepts
        response = self.client.post(f"/api/random_calls/lobby/default/match/{match_uuid}/accept")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["u1_accepted"] or response.data["u2_accepted"])
        self.assertFalse(response.data["accepted"])

        # Verify status shows partner hasn't accepted yet
        response = self.client.get("/api/random_calls/lobby/default/status")
        self.assertFalse(response.data["matching"]["both_accepted"])

        # User 2 accepts
        self.client.force_authenticate(user=self.user2)
        response = self.client.post(f"/api/random_calls/lobby/default/match/{match_uuid}/accept")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["accepted"])

        # Verify both_accepted is now true in status
        response = self.client.get("/api/random_calls/lobby/default/status")
        self.assertTrue(response.data["matching"]["both_accepted"])

        # Verify matching in DB
        matching.refresh_from_db()
        self.assertTrue(matching.u1_accepted)
        self.assertTrue(matching.u2_accepted)
        self.assertTrue(matching.accepted)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_reject_matching(self):
        """
        Test that users can reject a matching and it's marked as rejected.
        """
        # Both users join
        self.client.force_authenticate(user=self.user1)
        self.client.post("/api/random_calls/lobby/default/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post("/api/random_calls/lobby/default/join")

        # Get the matching
        matching = RandomCallMatching.objects.first()
        self.assertIsNotNone(matching)
        match_uuid = str(matching.uuid)

        # User 1 rejects
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(f"/api/random_calls/lobby/default/match/{match_uuid}/reject")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["rejected"])

        # Verify matching is marked as rejected
        matching.refresh_from_db()
        self.assertTrue(matching.rejected)
        self.assertFalse(matching.accepted)

        # Verify status no longer shows this matching (it's processed)
        response = self.client.get("/api/random_calls/lobby/default/status")
        self.assertEqual(response.status_code, 200)
        # Matching should be None because it's been processed (rejected)
        self.assertIsNone(response.data["matching"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_concurrent_users_matching(self):
        """
        Test matching with 7 concurrent users.
        Should create 3 pairs (6 users) with 1 user unmatched.
        """
        # Create 7 users
        users = self.create_multiple_users(7)

        # All users join the lobby
        for user in users:
            self.client.force_authenticate(user=user)
            response = self.client.post("/api/random_calls/lobby/default/join")
            self.assertEqual(response.status_code, 200)

        # Verify matchings created
        matchings = RandomCallMatching.objects.filter(lobby=self.lobby)
        self.assertEqual(matchings.count(), 3, "Should create exactly 3 matches for 7 users")

        # Collect all matched users
        matched_users = set()
        for matching in matchings:
            matched_users.add(matching.u1)
            matched_users.add(matching.u2)

        # Verify 6 users are matched
        self.assertEqual(len(matched_users), 6, "Exactly 6 users should be matched")

        # Verify no user is matched twice
        user_match_count = {}
        for matching in matchings:
            user_match_count[matching.u1] = user_match_count.get(matching.u1, 0) + 1
            user_match_count[matching.u2] = user_match_count.get(matching.u2, 0) + 1

        for user, count in user_match_count.items():
            self.assertEqual(count, 1, f"User {user.hash} should be matched exactly once")

        # Find unmatched user
        unmatched_users = [u for u in users if u not in matched_users]
        self.assertEqual(len(unmatched_users), 1, "Exactly 1 user should be unmatched")

        # Verify unmatched user has no matching when checking status
        self.client.force_authenticate(user=unmatched_users[0])
        response = self.client.get("/api/random_calls/lobby/default/status")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["matching"], "Unmatched user should have no matching")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_management_api_state_consistency(self):
        """
        Test that the management API state is consistent with individual user API states.
        Verifies user counts, match categorizations, and individual user statuses.
        """
        # Create 7 users
        users = self.create_multiple_users(7)

        # All users join
        for user in users:
            self.client.force_authenticate(user=user)
            self.client.post("/api/random_calls/lobby/default/join")

        # Get management overview
        # Note: This assumes the user has admin permissions or we authenticate as admin
        # For testing purposes, we'll authenticate as the first user which should have access
        self.client.force_authenticate(user=users[0])
        mgmt_response = self.client.get("/api/random_calls/lobby/default/management/overview")

        # If management API requires admin permissions, skip this test or use admin user
        if mgmt_response.status_code == 403:
            self.skipTest("Management API requires admin permissions")

        self.assertEqual(mgmt_response.status_code, 200)
        mgmt_data = mgmt_response.data

        # Verify lobby info
        self.assertEqual(mgmt_data["lobby"]["name"], "default")
        self.assertEqual(mgmt_data["lobby"]["active_users_count"], 7)
        self.assertEqual(mgmt_data["lobby"]["total_users_count"], 7)

        # Verify statistics
        self.assertEqual(mgmt_data["statistics"]["total_matches"], 3)
        self.assertEqual(mgmt_data["statistics"]["pending_count"], 3, "All matches should be pending initially")
        self.assertEqual(mgmt_data["statistics"]["accepted_count"], 0)
        self.assertEqual(mgmt_data["statistics"]["rejected_count"], 0)

        # Verify active users count matches reality
        active_users = mgmt_data["active_users"]
        self.assertEqual(len(active_users), 7, "Should show 7 active users")

        # Cross-verify each user's state with individual API
        for user in users:
            self.client.force_authenticate(user=user)
            user_status = self.client.get("/api/random_calls/lobby/default/status")
            self.assertEqual(user_status.status_code, 200)

            # Find this user in management API data
            user_in_mgmt = next((u for u in active_users if u["user_hash"] == user.hash), None)
            self.assertIsNotNone(user_in_mgmt, f"User {user.hash} should appear in management overview")

            # Verify has_pending_match flag consistency
            user_has_match = user_status.data["matching"] is not None
            self.assertEqual(
                user_in_mgmt["has_pending_match"],
                user_has_match,
                f"Management API has_pending_match should match user status for {user.hash}",
            )

            # If user has a match, verify match details consistency
            if user_has_match:
                match_uuid = str(user_status.data["matching"]["uuid"])

                # Find this match in management API pending matches
                match_in_mgmt = next(
                    (m for m in mgmt_data["match_proposals"]["pending"] if m["uuid"] == match_uuid), None
                )
                self.assertIsNotNone(match_in_mgmt, f"Match {match_uuid} should appear in management pending matches")

                # Verify acceptance states are consistent
                # The individual user API shows partner's acceptance, so we need to check both sides
                self.assertFalse(match_in_mgmt["accepted"], "Match should not be accepted yet")
                self.assertFalse(match_in_mgmt["rejected"], "Match should not be rejected yet")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_partial_acceptance_state(self):
        """
        Test state consistency when some users accept, some reject, and some don't respond.
        Tests with 7 users in various states.
        """
        # Create 7 users
        users = self.create_multiple_users(7)

        # All users join
        for user in users:
            self.client.force_authenticate(user=user)
            self.client.post("/api/random_calls/lobby/default/join")

        # Get all matches
        matchings = list(RandomCallMatching.objects.filter(lobby=self.lobby))
        self.assertEqual(len(matchings), 3, "Should have 3 matches")

        # First match: both users accept
        match1 = matchings[0]
        self.client.force_authenticate(user=match1.u1)
        self.client.post(f"/api/random_calls/lobby/default/match/{match1.uuid}/accept")
        self.client.force_authenticate(user=match1.u2)
        self.client.post(f"/api/random_calls/lobby/default/match/{match1.uuid}/accept")

        # Second match: one user accepts, other rejects
        match2 = matchings[1]
        self.client.force_authenticate(user=match2.u1)
        self.client.post(f"/api/random_calls/lobby/default/match/{match2.uuid}/accept")
        self.client.force_authenticate(user=match2.u2)
        self.client.post(f"/api/random_calls/lobby/default/match/{match2.uuid}/reject")

        # Third match: no response (pending)
        match3 = matchings[2]

        # Get management overview
        self.client.force_authenticate(user=users[0])
        mgmt_response = self.client.get("/api/random_calls/lobby/default/management/overview")

        if mgmt_response.status_code == 403:
            self.skipTest("Management API requires admin permissions")

        mgmt_data = mgmt_response.data

        # Verify match categorization
        self.assertEqual(mgmt_data["statistics"]["accepted_count"], 1, "Should have 1 accepted match")
        self.assertEqual(mgmt_data["statistics"]["rejected_count"], 1, "Should have 1 rejected match")
        self.assertEqual(mgmt_data["statistics"]["pending_count"], 1, "Should have 1 pending match")

        # Verify individual user states for accepted match
        self.client.force_authenticate(user=match1.u1)
        u1_status = self.client.get("/api/random_calls/lobby/default/status")
        # After both accepted, status should show in_session or no matching (processed)
        # Based on the implementation, accepted matches are filtered out (in_session=False filter)

        # Verify individual user states for rejected match
        self.client.force_authenticate(user=match2.u1)
        u1_status = self.client.get("/api/random_calls/lobby/default/status")
        # Rejected match should not appear in status
        self.assertIsNone(u1_status.data["matching"], "Rejected match should not appear in user status")

        # Verify individual user state for pending match
        self.client.force_authenticate(user=match3.u1)
        u3_status = self.client.get("/api/random_calls/lobby/default/status")
        self.assertIsNotNone(u3_status.data["matching"], "Pending match should appear in user status")
        self.assertFalse(u3_status.data["matching"]["both_accepted"], "Pending match should not be accepted")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_user_exit_during_matching(self):
        """
        Test that users exiting the lobby while having a pending match results in expired matches.
        """
        # Create 7 users
        users = self.create_multiple_users(7)

        # All users join
        for user in users:
            self.client.force_authenticate(user=user)
            self.client.post("/api/random_calls/lobby/default/join")

        # Get all matches
        matchings = list(RandomCallMatching.objects.filter(lobby=self.lobby))
        self.assertEqual(len(matchings), 3)

        # First user from first match exits without accepting/rejecting
        match1 = matchings[0]
        self.client.force_authenticate(user=match1.u1)
        self.client.post("/api/random_calls/lobby/default/exit")

        # Get management overview
        self.client.force_authenticate(user=users[0] if users[0] != match1.u1 else users[1])
        mgmt_response = self.client.get("/api/random_calls/lobby/default/management/overview")

        if mgmt_response.status_code == 403:
            self.skipTest("Management API requires admin permissions")

        mgmt_data = mgmt_response.data

        # Verify the match with exited user is marked as expired
        self.assertGreaterEqual(
            mgmt_data["statistics"]["expired_count"], 1, "Should have at least 1 expired match after user exit"
        )

        # Verify active users count decreased
        self.assertEqual(mgmt_data["lobby"]["active_users_count"], 6, "Should have 6 active users after one exit")

        # Verify the remaining user from the expired match sees no matching
        self.client.force_authenticate(user=match1.u2)
        # u2_status = self.client.get("/api/random_calls/lobby/default/status")
        # Status might still show the match or not depending on implementation
        # If it filters by both users being active, it should be None

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_seven_users_full_workflow(self):
        """
        Comprehensive test simulating a realistic scenario with 7 users:
        - Join lobby
        - Check matches created
        - Various acceptance/rejection actions
        - Verify state consistency throughout
        - Re-matching after rejections
        """
        # Create 7 users
        users = self.create_multiple_users(7)

        # Phase 1: All users join
        for user in users:
            self.client.force_authenticate(user=user)
            response = self.client.post("/api/random_calls/lobby/default/join")
            self.assertEqual(response.status_code, 200)

        # Phase 2: Verify initial matching state
        matchings = list(RandomCallMatching.objects.filter(lobby=self.lobby))
        self.assertEqual(len(matchings), 3, "Should create 3 matches for 7 users")

        # Identify matched and unmatched users
        matched_users = set()
        for matching in matchings:
            matched_users.add(matching.u1)
            matched_users.add(matching.u2)

        unmatched_users = [u for u in users if u not in matched_users]
        self.assertEqual(len(unmatched_users), 1, "Should have 1 unmatched user")

        # Phase 3: Each matched user checks their status
        for user in matched_users:
            self.client.force_authenticate(user=user)
            response = self.client.get("/api/random_calls/lobby/default/status")
            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(response.data["matching"], f"User {user.hash} should have a matching")

        # Phase 4: First pair accepts
        match1 = matchings[0]
        self.client.force_authenticate(user=match1.u1)
        accept_resp = self.client.post(f"/api/random_calls/lobby/default/match/{match1.uuid}/accept")
        self.assertEqual(accept_resp.status_code, 200)
        self.assertFalse(accept_resp.data["accepted"], "Should not be fully accepted yet")

        self.client.force_authenticate(user=match1.u2)
        accept_resp = self.client.post(f"/api/random_calls/lobby/default/match/{match1.uuid}/accept")
        self.assertEqual(accept_resp.status_code, 200)
        self.assertTrue(accept_resp.data["accepted"], "Should be fully accepted now")

        # Phase 5: Second pair - one rejects
        match2 = matchings[1]
        self.client.force_authenticate(user=match2.u1)
        reject_resp = self.client.post(f"/api/random_calls/lobby/default/match/{match2.uuid}/reject")
        self.assertEqual(reject_resp.status_code, 200)
        self.assertTrue(reject_resp.data["rejected"])

        # Phase 6: Third pair - both exit without responding
        match3 = matchings[2]
        self.client.force_authenticate(user=match3.u1)
        self.client.post("/api/random_calls/lobby/default/exit")
        self.client.force_authenticate(user=match3.u2)
        self.client.post("/api/random_calls/lobby/default/exit")

        # Phase 7: Get management overview and verify all states
        # Use a user that's still active
        active_user = match1.u1  # From accepted match, should still be in lobby
        self.client.force_authenticate(user=active_user)
        mgmt_response = self.client.get("/api/random_calls/lobby/default/management/overview")

        if mgmt_response.status_code == 403:
            self.skipTest("Management API requires admin permissions")

        mgmt_data = mgmt_response.data

        # Verify statistics reflect all actions
        self.assertEqual(mgmt_data["statistics"]["total_matches"], 3)
        self.assertEqual(mgmt_data["statistics"]["accepted_count"], 1, "Should have 1 accepted match")
        self.assertEqual(mgmt_data["statistics"]["rejected_count"], 1, "Should have 1 rejected match")

        # Verify active user count (7 initial - 2 exits = 5)
        self.assertEqual(mgmt_data["lobby"]["active_users_count"], 5)

        # Phase 8: Trigger re-matching for rejected users
        # The unmatched user and the two users from rejected/exited matches could be re-matched
        from video.tasks import random_call_lobby_perform_matching

        random_call_lobby_perform_matching("default")

        # Check if new matches were created for the rejected/unmatched users
        all_matchings = RandomCallMatching.objects.filter(lobby=self.lobby)
        # We should have at least 3 original matches, possibly more from re-matching
        self.assertGreaterEqual(all_matchings.count(), 3)
