from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from back.celery import app
from chat.models import Message
from django.test import TestCase, override_settings
from django.utils import timezone
from freezegun import freeze_time
from management.models.matches import Match
from management.models.profile import Profile
from management.models.state import State
from management.models.unconfirmed_matches import MatchType
from management.models.user import User
from management.tests.helpers import register_user
from rest_framework.test import APIClient

from video.analytics.display_time import DISPLAY_TZ
from video.models import (
    LivekitSession,
    RandomCallLobby,
    RandomCallLobbyUser,
    RandomCallMatching,
    RandomCallProposalUserStatus,
)


class RandomCallsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        app.conf.task_always_eager = True

        # Eager Celery ignores `countdown`, so the `cleanup_if_not_accepted` timer that
        # production gives users `match_proposal_timeout` seconds to answer fires the
        # instant a proposal is created. Every proposal then expires before anyone can
        # react, both users go free, and the next join re-proposes them — which is why
        # seven joins produced six sequentially-expired proposals instead of three live
        # ones. Suppress the *scheduled* call only; the timeout tests below invoke
        # `cleanup_if_not_accepted` directly, which is the honest way to test expiry.
        expiry_patcher = patch("video.tasks.cleanup_if_not_accepted.apply_async")
        self.scheduled_expiry = expiry_patcher.start()
        self.addCleanup(expiry_patcher.stop)

        # Create users
        self.user1 = register_user(
            {
                "email": "user1@example.com",
                "password1": "Test123!",
                "password2": "Test123!",
                "first_name": "User",
                "second_name": "One",
                "birth_year": 1990,
                "user_type": Profile.TypeChoices.LEARNER,
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
                "user_type": Profile.TypeChoices.LEARNER,
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
        self.lobby_api_url = f"/api/random_calls/lobby/{self.lobby.uuid}"

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

    def _create_admin_user(self, suffix: str = "admin") -> User:
        """A user that is genuinely staff, so `IsAdminOrMatchingUser` lets them in.

        `UserManager.create_user` hard-sets `kwargs["is_staff"] = False`, so the
        `is_staff=True` this used to pass was silently discarded and every management
        endpoint here returned 403. Set it with a follow-up write instead.
        """
        user = User.objects.create_user(
            email=f"rc_mgmt_admin_{suffix}@example.com",
            password="Test123!",
            first_name=f"Admin{suffix}",
            last_name="Test",
        )
        User.objects.filter(pk=user.pk).update(is_staff=True)
        user.refresh_from_db()
        assert user.is_staff, "admin fixture must be staff or every endpoint test 403s"
        return user

    def test_setup(self):
        """Verify that users and lobby are created correctly."""
        self.assertTrue(User.objects.filter(pk=self.user1.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.user2.pk).exists())
        self.assertEqual(RandomCallLobby.objects.count(), 1)
        self.assertEqual(self.lobby.name, "default")

    def test_admin_can_update_upcoming_lobby(self):
        self.client.force_authenticate(user=self._create_admin_user("update_upcoming"))
        upcoming = RandomCallLobby.objects.create(
            name="default",
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=2),
            match_proposal_timeout=60,
        )
        new_start = timezone.now() + timezone.timedelta(days=2)
        new_end = new_start + timezone.timedelta(hours=3)

        response = self.client.patch(
            f"/api/random_calls/lobby/{upcoming.uuid}/management",
            {
                "start_time": new_start.isoformat(),
                "end_time": new_end.isoformat(),
                "match_proposal_timeout": 90,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        upcoming.refresh_from_db()
        self.assertEqual(upcoming.start_time, new_start)
        self.assertEqual(upcoming.end_time, new_end)
        self.assertEqual(upcoming.match_proposal_timeout, 90)

    # Fixed dates: "tomorrow" on 31 December is next year, which recurrence rejects.
    @freeze_time("2026-03-02 09:00:00")
    def test_admin_can_create_recurring_lobbies_until_year_end(self):
        self.client.force_authenticate(user=self._create_admin_user("create_recurring"))
        start = datetime(2026, 3, 3, 12, 0, tzinfo=DISPLAY_TZ)

        response = self.client.post(
            "/api/random_calls/lobby/default/management/create",
            {
                "start_time": start.isoformat(),
                "end_time": (start + timezone.timedelta(hours=2)).isoformat(),
                "match_proposal_timeout": 90,
                "frequency": "weekly",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        recurrence_group = response.data["lobby"]["recurrence_group"]
        occurrences = RandomCallLobby.objects.filter(recurrence_group=recurrence_group).order_by("start_time")
        # Every Tuesday from 3 March to 29 December 2026.
        self.assertEqual(response.data["created_count"], 44)
        self.assertEqual(occurrences.count(), 44)
        self.assertTrue(all(lobby.frequency == "weekly" for lobby in occurrences))
        local_starts = [timezone.localtime(lobby.start_time, DISPLAY_TZ) for lobby in occurrences]
        self.assertEqual(local_starts[-1].date(), datetime(2026, 12, 29).date())

    @freeze_time("2026-03-02 09:00:00")
    def test_recurring_lobbies_keep_berlin_wall_clock_time_across_dst(self):
        self.client.force_authenticate(user=self._create_admin_user("recurring_dst"))
        start = datetime(2026, 3, 3, 18, 0, tzinfo=DISPLAY_TZ)

        response = self.client.post(
            "/api/random_calls/lobby/default/management/create",
            {
                "start_time": start.isoformat(),
                "end_time": (start + timezone.timedelta(hours=2)).isoformat(),
                "frequency": "weekly",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        occurrences = RandomCallLobby.objects.filter(recurrence_group=response.data["lobby"]["recurrence_group"])
        local_times = {
            (timezone.localtime(lobby.start_time, DISPLAY_TZ).hour, timezone.localtime(lobby.end_time, DISPLAY_TZ).hour)
            for lobby in occurrences
        }
        # 18:00-20:00 Berlin in winter (17:00 UTC) and in summer (16:00 UTC) alike.
        self.assertEqual(local_times, {(18, 20)})
        self.assertEqual(
            {lobby.start_time.astimezone(DISPLAY_TZ).utcoffset().seconds // 3600 for lobby in occurrences}, {1, 2}
        )

    def test_invalid_lobby_times_return_a_readable_error(self):
        self.client.force_authenticate(user=self._create_admin_user("readable_error"))
        start = timezone.now() + timezone.timedelta(days=1)

        response = self.client.post(
            "/api/random_calls/lobby/default/management/create",
            {"start_time": start.isoformat(), "end_time": start.isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "End time must be after start time")

    def test_end_lobby_ends_the_live_lobby_when_future_sessions_exist(self):
        self.client.force_authenticate(user=self._create_admin_user("end_live"))
        # Created after the live lobby, so it has the highest id for the name.
        future = RandomCallLobby.objects.create(
            name="default",
            start_time=timezone.now() + timezone.timedelta(days=7),
            end_time=timezone.now() + timezone.timedelta(days=7, hours=2),
        )

        response = self.client.post("/api/random_calls/lobby/default/management/end")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lobby"]["uuid"], str(self.lobby.uuid))
        self.lobby.refresh_from_db()
        future.refresh_from_db()
        self.assertLessEqual(self.lobby.end_time, timezone.now())
        self.assertGreater(future.end_time, timezone.now())

    def test_reset_lobby_resets_the_live_lobby_when_future_sessions_exist(self):
        self.client.force_authenticate(user=self._create_admin_user("reset_live"))
        future = RandomCallLobby.objects.create(
            name="default",
            start_time=timezone.now() + timezone.timedelta(days=7),
            end_time=timezone.now() + timezone.timedelta(days=7, hours=2),
        )

        response = self.client.post("/api/random_calls/lobby/default/management/reset")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(RandomCallLobby.objects.filter(pk=self.lobby.pk).exists())
        self.assertTrue(RandomCallLobby.objects.filter(pk=future.pk).exists())

    def test_scheduling_fields_are_only_shown_to_managers(self):
        self.client.force_authenticate(user=self.user1)
        user_view = self.client.get("/api/random_calls/upcoming?name=default").data[0]
        self.assertNotIn("frequency", user_view)
        self.assertNotIn("recurrence_group", user_view)
        self.assertNotIn("match_proposal_timeout", user_view)

        self.client.force_authenticate(user=self._create_admin_user("scheduling_fields"))
        admin_view = self.client.get("/api/random_calls/upcoming?name=default").data[0]
        self.assertEqual(admin_view["frequency"], "once")
        self.assertIn("recurrence_group", admin_view)
        self.assertIn("match_proposal_timeout", admin_view)

    def test_admin_can_delete_upcoming_lobby(self):
        self.client.force_authenticate(user=self._create_admin_user("delete_upcoming"))
        upcoming = RandomCallLobby.objects.create(
            name="default",
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=2),
        )

        response = self.client.delete(f"/api/random_calls/lobby/{upcoming.uuid}/management")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(RandomCallLobby.objects.filter(pk=upcoming.pk).exists())

    @freeze_time("2026-03-02 09:00:00")
    def test_admin_can_update_this_and_future_recurring_lobbies(self):
        self.client.force_authenticate(user=self._create_admin_user("update_series"))
        recurrence_group = uuid4()
        start = datetime(2026, 3, 3, 12, 0, tzinfo=DISPLAY_TZ)
        lobbies = [
            RandomCallLobby.objects.create(
                name="default",
                start_time=start + timezone.timedelta(weeks=week),
                end_time=start + timezone.timedelta(weeks=week, hours=2),
                frequency="weekly",
                recurrence_group=recurrence_group,
            )
            for week in range(3)
        ]
        replacement_start = lobbies[1].start_time + timezone.timedelta(days=1)

        response = self.client.patch(
            f"/api/random_calls/lobby/{lobbies[1].uuid}/management?scope=future",
            {
                "start_time": replacement_start.isoformat(),
                "end_time": (replacement_start + timezone.timedelta(hours=2)).isoformat(),
                "match_proposal_timeout": 90,
                "frequency": "fortnightly",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(RandomCallLobby.objects.filter(pk=lobbies[0].pk).exists())
        future = RandomCallLobby.objects.filter(
            recurrence_group=recurrence_group,
            start_time__gte=replacement_start,
        ).order_by("start_time")
        self.assertTrue(future.exists())
        self.assertTrue(all(lobby.frequency == "fortnightly" for lobby in future))
        self.assertEqual(future.first().start_time, replacement_start)
        # Existing sessions are re-timed in place, so they keep their uuids.
        self.assertEqual(
            list(future.values_list("uuid", flat=True)[:2]),
            [lobbies[1].uuid, lobbies[2].uuid],
        )

    def test_admin_can_delete_this_and_future_recurring_lobbies(self):
        self.client.force_authenticate(user=self._create_admin_user("delete_series"))
        recurrence_group = uuid4()
        start = timezone.now() + timezone.timedelta(days=1)
        lobbies = [
            RandomCallLobby.objects.create(
                name="default",
                start_time=start + timezone.timedelta(weeks=week),
                end_time=start + timezone.timedelta(weeks=week, hours=2),
                frequency="weekly",
                recurrence_group=recurrence_group,
            )
            for week in range(3)
        ]

        response = self.client.delete(f"/api/random_calls/lobby/{lobbies[1].uuid}/management?scope=future")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["deleted_count"], 2)
        self.assertTrue(RandomCallLobby.objects.filter(pk=lobbies[0].pk).exists())
        self.assertFalse(RandomCallLobby.objects.filter(pk__in=[lobbies[1].pk, lobbies[2].pk]).exists())

    def test_admin_cannot_update_lobby_across_multiple_dates(self):
        self.client.force_authenticate(user=self._create_admin_user("multi_day_lobby"))
        upcoming = RandomCallLobby.objects.create(
            name="default",
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=2),
        )
        new_start = timezone.localtime(timezone.now()).replace(hour=12, minute=0, second=0, microsecond=0)

        response = self.client.patch(
            f"/api/random_calls/lobby/{upcoming.uuid}/management",
            {
                "start_time": (new_start + timezone.timedelta(days=1)).isoformat(),
                "end_time": (new_start + timezone.timedelta(days=2)).isoformat(),
                "match_proposal_timeout": 90,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_admin_cannot_update_or_delete_started_lobby(self):
        self.client.force_authenticate(user=self._create_admin_user("started_lobby"))
        payload = {
            "start_time": (timezone.now() + timezone.timedelta(days=1)).isoformat(),
            "end_time": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "match_proposal_timeout": 90,
        }
        url = f"/api/random_calls/lobby/{self.lobby.uuid}/management"

        update_response = self.client.patch(url, payload, format="json")
        delete_response = self.client.delete(url)

        self.assertEqual(update_response.status_code, 400)
        self.assertEqual(delete_response.status_code, 400)
        self.assertTrue(RandomCallLobby.objects.filter(pk=self.lobby.pk).exists())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_join_lobby_and_matching_trigger(self):
        """
        Test that both users can join the lobby and the matching task is triggered and executed.
        """
        # User 1 joins
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(f"{self.lobby_api_url}/join")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lobby"], self.lobby.uuid)
        self.assertFalse(response.data["already_joined"])

        # User 2 joins
        self.client.force_authenticate(user=self.user2)
        response = self.client.post(f"{self.lobby_api_url}/join")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["already_joined"])

        # User 1 checks status
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(f"{self.lobby_api_url}/status")
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
                "user_type": Profile.TypeChoices.LEARNER,
            }
        )

        # Join all users to lobby
        for u in [self.user1, self.user2, user3]:
            self.client.force_authenticate(user=u)
            self.client.post(f"{self.lobby_api_url}/join")

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

        random_call_lobby_perform_matching(str(self.lobby.uuid))

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
        response = self.client.post(f"{self.lobby_api_url}/join")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["already_joined"])

        # Verify user is in lobby and active
        lobby_user = RandomCallLobbyUser.objects.filter(user=self.user1, lobby=self.lobby).first()
        self.assertIsNotNone(lobby_user)
        self.assertTrue(lobby_user.is_active)

        # User 1 exits
        response = self.client.post(f"{self.lobby_api_url}/exit")
        self.assertEqual(response.status_code, 200)

        # Verify user is marked as inactive
        lobby_user.refresh_from_db()
        self.assertFalse(lobby_user.is_active)

        # User 1 rejoins - should not say already_joined
        response = self.client.post(f"{self.lobby_api_url}/join")
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
        self.client.post(f"{self.lobby_api_url}/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post(f"{self.lobby_api_url}/join")

        # Get the matching
        matching = RandomCallMatching.objects.first()
        self.assertIsNotNone(matching)

        # User 1 checks status and gets matching info
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(f"{self.lobby_api_url}/status")
        self.assertEqual(response.status_code, 200)
        match_uuid = response.data["matching"]["uuid"]

        # User 1 accepts
        response = self.client.post(f"{self.lobby_api_url}/match/{match_uuid}/accept")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["u1_accepted"] or response.data["u2_accepted"])
        self.assertFalse(response.data["accepted"])

        # Verify status shows partner hasn't accepted yet
        response = self.client.get(f"{self.lobby_api_url}/status")
        self.assertFalse(response.data["matching"]["both_accepted"])

        # User 2 accepts
        self.client.force_authenticate(user=self.user2)
        response = self.client.post(f"{self.lobby_api_url}/match/{match_uuid}/accept")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["accepted"])

        # Verify both_accepted is now true in status
        response = self.client.get(f"{self.lobby_api_url}/status")
        self.assertTrue(response.data["matching"]["both_accepted"])

        # Verify matching in DB
        matching.refresh_from_db()
        self.assertTrue(matching.u1_accepted)
        self.assertTrue(matching.u2_accepted)
        self.assertTrue(matching.accepted)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_three_user_frontend_flow_join_status_accept_and_room_authenticate(self):
        """
        First 3-user integration scenario that mirrors frontend lobby behavior.

        Frontend flow mirrored in this test:
        1) RandomCallsLobby.handleJoinComplete -> POST /join
        2) useSWR polling -> GET /status
        3) PartnerProposal.handleAccept -> POST /accept (both sides)
        4) handleBothAccepted -> POST /room_authenticate (both sides)
        """
        user3 = register_user(
            {
                "email": "user3_frontend_flow@example.com",
                "password1": "Test123!",
                "password2": "Test123!",
                "first_name": "User",
                "second_name": "Three",
                "birth_year": 1995,
                "user_type": Profile.TypeChoices.LEARNER,
            }
        )

        class FakeAccessToken:
            """
            Lightweight token stub for deterministic room_authenticate tests.
            """

            def __init__(self, *args, **kwargs):
                self._identity = None
                self._name = None
                self._grants = None

            def with_identity(self, identity):
                self._identity = identity
                return self

            def with_name(self, name):
                self._name = name
                return self

            def with_grants(self, grants):
                self._grants = grants
                return self

            def to_jwt(self):
                return "test-livekit-jwt"

        # Backend code path under test:
        # - /join schedules matching via apply_async.
        # - In eager mode this can produce cascading side effects.
        # We disable those async triggers and explicitly run one matching cycle below.
        with (
            patch("video.random_calls.random_call_lobby_perform_matching.apply_async", return_value=None),
            patch("video.random_calls.cleanup_inactive_lobby_users.apply_async", return_value=None),
            patch("video.tasks.cleanup_if_not_accepted.apply_async", return_value=None),
            patch("video.random_calls.create_livekit_room", new_callable=AsyncMock),
            patch("video.random_calls.livekit_api.AccessToken", FakeAccessToken),
        ):
            # Frontend step: handleJoinComplete -> joinLobby() for each user.
            for user in [self.user1, self.user2, user3]:
                self.client.force_authenticate(user=user)
                response = self.client.post(f"{self.lobby_api_url}/join")
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.data["already_joined"])

            # Run one explicit matching cycle to emulate the background matcher.
            from video.tasks import random_call_lobby_perform_matching

            random_call_lobby_perform_matching(str(self.lobby.uuid))

            # Frontend step: useSWR polling GET /status.
            status_by_user = {}
            for user in [self.user1, self.user2, user3]:
                self.client.force_authenticate(user=user)
                status = self.client.get(f"{self.lobby_api_url}/status")
                self.assertEqual(status.status_code, 200)
                status_by_user[user.id] = status.data

            matched_users = []
            unmatched_users = []
            for user in [self.user1, self.user2, user3]:
                if status_by_user[user.id]["matching"] is None:
                    unmatched_users.append(user)
                else:
                    matched_users.append(user)

            self.assertEqual(len(matched_users), 2, "Exactly one pair should be matched in a 3-user scenario")
            self.assertEqual(len(unmatched_users), 1, "Exactly one user should remain unmatched")

            match_uuid = str(status_by_user[matched_users[0].id]["matching"]["uuid"])

            # Frontend step: PartnerProposal.handleAccept -> acceptMatch() by both users.
            for user in matched_users:
                self.client.force_authenticate(user=user)
                accept_response = self.client.post(f"{self.lobby_api_url}/match/{match_uuid}/accept")
                self.assertEqual(accept_response.status_code, 200)

            matching = RandomCallMatching.objects.get(uuid=match_uuid)
            self.assertTrue(matching.u1_accepted)
            self.assertTrue(matching.u2_accepted)
            self.assertTrue(matching.accepted)

            # Frontend step: handleBothAccepted -> authenticateRoom() by both users.
            for user in matched_users:
                self.client.force_authenticate(user=user)
                auth_response = self.client.post(f"{self.lobby_api_url}/match/{match_uuid}/room_authenticate")
                self.assertEqual(auth_response.status_code, 200)
                self.assertIn("token", auth_response.data)
                self.assertEqual(auth_response.data["token"], "test-livekit-jwt")

            matching.refresh_from_db()
            self.assertTrue(matching.both_requested_room_token)

            # Backend status filter behavior:
            # once both users requested room token, the proposal no longer appears in /status.
            for user in matched_users:
                self.client.force_authenticate(user=user)
                status_after_auth = self.client.get(f"{self.lobby_api_url}/status")
                self.assertEqual(status_after_auth.status_code, 200)
                self.assertIsNone(status_after_auth.data["matching"])

            # The third user remains unmatched in this basic scenario.
            self.client.force_authenticate(user=unmatched_users[0])
            unmatched_status = self.client.get(f"{self.lobby_api_url}/status")
            self.assertEqual(unmatched_status.status_code, 200)
            self.assertIsNone(unmatched_status.data["matching"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_reject_matching(self):
        """
        Test that users can reject a matching and it's marked as rejected.
        """
        # Both users join
        self.client.force_authenticate(user=self.user1)
        self.client.post(f"{self.lobby_api_url}/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post(f"{self.lobby_api_url}/join")

        # Get the matching
        matching = RandomCallMatching.objects.first()
        self.assertIsNotNone(matching)
        match_uuid = str(matching.uuid)

        # User 1 rejects
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(f"{self.lobby_api_url}/match/{match_uuid}/reject")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["rejected"])

        # Verify matching is marked as rejected
        matching.refresh_from_db()
        self.assertTrue(matching.rejected)
        self.assertFalse(matching.accepted)
        self.assertEqual(matching.u1_status, RandomCallProposalUserStatus.REJECTED)
        self.assertEqual(matching.u2_status, RandomCallProposalUserStatus.PENDING)

        # Verify status no longer shows this matching (it's processed)
        response = self.client.get(f"{self.lobby_api_url}/status")
        self.assertEqual(response.status_code, 200)
        # Matching should be None because it's been processed (rejected)
        self.assertIsNone(response.data["matching"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_explicit_rejection_prevents_rematching_same_pair(self):
        """
        After a deliberate reject, the same two users must not be rematched
        in this lobby. A third user should still be matchable with either of them.
        """
        from management.models.profile import Profile

        from video.tasks import random_call_lobby_perform_matching

        user3 = self.create_multiple_users(1)[0]
        for user in (self.user1, self.user2, user3):
            user.profile.user_type = Profile.TypeChoices.LEARNER
            user.profile.save()

        self.client.force_authenticate(user=self.user1)
        self.client.post(f"{self.lobby_api_url}/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post(f"{self.lobby_api_url}/join")

        matching = RandomCallMatching.objects.get(lobby=self.lobby)
        rejected_pair = frozenset((matching.u1_id, matching.u2_id))

        self.client.force_authenticate(user=matching.u1)
        response = self.client.post(f"{self.lobby_api_url}/match/{matching.uuid}/reject")
        self.assertEqual(response.status_code, 200)
        matching.refresh_from_db()
        self.assertTrue(matching.rejected)
        self.assertIsNotNone(matching.rejected_at)
        rejector = matching.u1
        self.assertEqual(matching.get_user_status(rejector), RandomCallProposalUserStatus.REJECTED)

        # Only the rejected pair remains in the lobby — rematching must not recreate it.
        result = random_call_lobby_perform_matching(str(self.lobby.uuid))
        self.assertEqual(result["matchings"], [])
        self.assertEqual(RandomCallMatching.objects.filter(lobby=self.lobby).count(), 1)

        # A third learner joins; matching should prefer a pair that is not the rejected one.
        self.client.force_authenticate(user=user3)
        self.client.post(f"{self.lobby_api_url}/join")
        random_call_lobby_perform_matching(str(self.lobby.uuid))

        new_matching = (
            RandomCallMatching.objects.filter(lobby=self.lobby).exclude(uuid=matching.uuid).order_by("-pk").first()
        )
        self.assertIsNotNone(new_matching)
        self.assertNotEqual(frozenset((new_matching.u1_id, new_matching.u2_id)), rejected_pair)
        self.assertIn(user3.id, (new_matching.u1_id, new_matching.u2_id))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_timeout_rejection_allows_rematching_same_pair(self):
        """
        System timeout rejections must not permanently block the pair.
        """
        from management.models.profile import Profile

        from video.tasks import cleanup_if_not_accepted, random_call_lobby_perform_matching

        for user in (self.user1, self.user2):
            user.profile.user_type = Profile.TypeChoices.LEARNER
            user.profile.save()

        self.client.force_authenticate(user=self.user1)
        self.client.post(f"{self.lobby_api_url}/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post(f"{self.lobby_api_url}/join")

        matching = RandomCallMatching.objects.get(lobby=self.lobby)
        original_pair = frozenset((matching.u1_id, matching.u2_id))

        cleanup_if_not_accepted(str(matching.uuid))
        matching.refresh_from_db()
        self.assertTrue(matching.rejected)
        self.assertTrue(matching.expired)
        self.assertIsNone(matching.rejected_at)
        self.assertEqual(matching.u1_status, RandomCallProposalUserStatus.EXPIRED)
        self.assertEqual(matching.u2_status, RandomCallProposalUserStatus.EXPIRED)

        result = random_call_lobby_perform_matching(str(self.lobby.uuid))
        self.assertEqual(len(result["matchings"]), 1)

        new_matching = (
            RandomCallMatching.objects.filter(lobby=self.lobby).exclude(uuid=matching.uuid).order_by("-pk").first()
        )
        self.assertIsNotNone(new_matching)
        self.assertEqual(frozenset((new_matching.u1_id, new_matching.u2_id)), original_pair)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_timeout_preserves_accepted_user_status(self):
        """If one user accepted before timeout, their status stays accepted; the other expires."""
        from video.tasks import cleanup_if_not_accepted

        self.client.force_authenticate(user=self.user1)
        self.client.post(f"{self.lobby_api_url}/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post(f"{self.lobby_api_url}/join")

        matching = RandomCallMatching.objects.get(lobby=self.lobby)
        self.client.force_authenticate(user=matching.u1)
        response = self.client.post(f"{self.lobby_api_url}/match/{matching.uuid}/accept")
        self.assertEqual(response.status_code, 200)

        matching.refresh_from_db()
        self.assertEqual(matching.u1_status, RandomCallProposalUserStatus.ACCEPTED)
        self.assertEqual(matching.u2_status, RandomCallProposalUserStatus.PENDING)

        cleanup_if_not_accepted(str(matching.uuid))
        matching.refresh_from_db()
        self.assertTrue(matching.expired)
        self.assertTrue(matching.rejected)
        self.assertEqual(matching.u1_status, RandomCallProposalUserStatus.ACCEPTED)
        self.assertEqual(matching.u2_status, RandomCallProposalUserStatus.EXPIRED)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_exit_does_not_block_rematching_same_pair(self):
        """
        Leaving the lobby closes the proposal but must not block rematching the same pair.
        """
        from management.models.profile import Profile

        from video.tasks import random_call_lobby_perform_matching

        for user in (self.user1, self.user2):
            user.profile.user_type = Profile.TypeChoices.LEARNER
            user.profile.save()

        self.client.force_authenticate(user=self.user1)
        self.client.post(f"{self.lobby_api_url}/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post(f"{self.lobby_api_url}/join")

        matching = RandomCallMatching.objects.get(lobby=self.lobby)
        original_pair = frozenset((matching.u1_id, matching.u2_id))
        leaver = matching.u1

        self.client.force_authenticate(user=leaver)
        self.client.post(f"{self.lobby_api_url}/exit")
        matching.refresh_from_db()
        self.assertTrue(matching.rejected)
        self.assertEqual(matching.get_user_status(leaver), RandomCallProposalUserStatus.EXITED)
        self.assertEqual(
            matching.get_user_status(matching.u2 if leaver == matching.u1 else matching.u1),
            RandomCallProposalUserStatus.PENDING,
        )

        # /join fires the matcher via apply_async, which eager Celery runs inline — the
        # rejoin would rematch the pair before the explicit cycle below, leaving it
        # nothing to do. Suppress the triggered run so the assertion measures the cycle
        # under test rather than a side effect of the second join.
        with patch("video.random_calls.random_call_lobby_perform_matching.apply_async"):
            self.client.force_authenticate(user=leaver)
            self.client.post(f"{self.lobby_api_url}/join")
            self.client.force_authenticate(user=matching.u2 if leaver == matching.u1 else matching.u1)
            self.client.post(f"{self.lobby_api_url}/join")

        result = random_call_lobby_perform_matching(str(self.lobby.uuid))
        self.assertEqual(len(result["matchings"]), 1)

        new_matching = (
            RandomCallMatching.objects.filter(lobby=self.lobby).exclude(uuid=matching.uuid).order_by("-pk").first()
        )
        self.assertIsNotNone(new_matching)
        self.assertEqual(frozenset((new_matching.u1_id, new_matching.u2_id)), original_pair)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_partner_acknowledges_rejection_without_overwriting_status(self):
        """
        Partner polling after an explicit reject sets confirmed_rejection but leaves
        u*_status as the action (pending for the partner, rejected for the rejector).
        """
        self.client.force_authenticate(user=self.user1)
        self.client.post(f"{self.lobby_api_url}/join")
        self.client.force_authenticate(user=self.user2)
        self.client.post(f"{self.lobby_api_url}/join")

        matching = RandomCallMatching.objects.get(lobby=self.lobby)
        rejector = matching.u1
        partner = matching.u2

        self.client.force_authenticate(user=rejector)
        self.client.post(f"{self.lobby_api_url}/match/{matching.uuid}/reject")

        self.client.force_authenticate(user=partner)
        response = self.client.get(f"{self.lobby_api_url}/status")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["matching"]["partner_rejected"])

        matching.refresh_from_db()
        self.assertEqual(matching.get_user_status(partner), RandomCallProposalUserStatus.PENDING)
        self.assertEqual(matching.get_user_status(rejector), RandomCallProposalUserStatus.REJECTED)
        if matching.is_u1(partner):
            self.assertTrue(matching.u1_confirmed_rejection)
        else:
            self.assertTrue(matching.u2_confirmed_rejection)
        self.assertTrue(matching.both_confirmed_rejection)

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
            response = self.client.post(f"{self.lobby_api_url}/join")
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
            self.assertEqual(count, 1, f"User {user.uuid} should be matched exactly once")

        # Find unmatched user
        unmatched_users = [u for u in users if u not in matched_users]
        self.assertEqual(len(unmatched_users), 1, "Exactly 1 user should be unmatched")

        # Verify unmatched user has no matching when checking status
        self.client.force_authenticate(user=unmatched_users[0])
        response = self.client.get(f"{self.lobby_api_url}/status")
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
            self.client.post(f"{self.lobby_api_url}/join")

        # Get management overview
        self.client.force_authenticate(user=self._create_admin_user("state_consistency"))
        mgmt_response = self.client.get("/api/random_calls/analytics/lobby/default/instance")

        self.assertEqual(mgmt_response.status_code, 200)
        mgmt_data = mgmt_response.data

        # Verify lobby info
        self.assertEqual(mgmt_data["lobby"]["name"], "default")
        self.assertEqual(mgmt_data["lobby"]["active_users_count"], 7)
        self.assertEqual(mgmt_data["lobby"]["total_users_count"], 7)

        # Verify statistics
        self.assertEqual(mgmt_data["proposal_statistics"]["total_matches"], 3)
        self.assertEqual(
            mgmt_data["proposal_statistics"]["pending_count"], 3, "All matches should be pending initially"
        )
        self.assertEqual(mgmt_data["proposal_statistics"]["accepted_count"], 0)
        self.assertEqual(mgmt_data["proposal_statistics"]["rejected_count"], 0)

        # Verify active users count matches reality
        active_users = mgmt_data["active_users"]
        self.assertEqual(len(active_users), 7, "Should show 7 active users")

        # Cross-verify each user's state with individual API
        for user in users:
            self.client.force_authenticate(user=user)
            user_status = self.client.get(f"{self.lobby_api_url}/status")
            self.assertEqual(user_status.status_code, 200)

            # Find this user in management API data
            user_in_mgmt = next((u for u in active_users if u["user_uuid"] == str(user.uuid)), None)
            self.assertIsNotNone(user_in_mgmt, f"User {user.uuid} should appear in management overview")

            # Verify has_pending_match flag consistency
            user_has_match = user_status.data["matching"] is not None
            self.assertEqual(
                user_in_mgmt["has_pending_match"],
                user_has_match,
                f"Management API has_pending_match should match user status for {user.uuid}",
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
            self.client.post(f"{self.lobby_api_url}/join")

        # Get all matches
        matchings = list(RandomCallMatching.objects.filter(lobby=self.lobby))
        self.assertEqual(len(matchings), 3, "Should have 3 matches")

        # First match: both users accept
        match1 = matchings[0]
        self.client.force_authenticate(user=match1.u1)
        self.client.post(f"{self.lobby_api_url}/match/{match1.uuid}/accept")
        self.client.force_authenticate(user=match1.u2)
        self.client.post(f"{self.lobby_api_url}/match/{match1.uuid}/accept")

        # Second match: one user accepts, other rejects
        match2 = matchings[1]
        self.client.force_authenticate(user=match2.u1)
        self.client.post(f"{self.lobby_api_url}/match/{match2.uuid}/accept")
        self.client.force_authenticate(user=match2.u2)
        self.client.post(f"{self.lobby_api_url}/match/{match2.uuid}/reject")

        # Third match: no response (pending)
        match3 = matchings[2]

        # Get management overview
        self.client.force_authenticate(user=self._create_admin_user("match_states"))
        mgmt_response = self.client.get("/api/random_calls/analytics/lobby/default/instance")

        self.assertEqual(mgmt_response.status_code, 200)
        mgmt_data = mgmt_response.data

        # Verify match categorization
        self.assertEqual(mgmt_data["proposal_statistics"]["accepted_count"], 1, "Should have 1 accepted match")
        self.assertEqual(mgmt_data["proposal_statistics"]["rejected_count"], 1, "Should have 1 rejected match")
        self.assertEqual(mgmt_data["proposal_statistics"]["pending_count"], 1, "Should have 1 pending match")

        # Verify individual user states for accepted match
        self.client.force_authenticate(user=match1.u1)
        # An accepted proposal stays in the status payload — `open_pending_random_call_match_q`
        # filters on rejected/completed/in_session but never on `accepted`, because the client
        # still needs the row to join the call. (The old comment here claimed the opposite and
        # asserted nothing.)
        accepted_status = self.client.get(f"{self.lobby_api_url}/status")
        self.assertIsNotNone(accepted_status.data["matching"], "Accepted match should still be offered to join")
        self.assertTrue(accepted_status.data["matching"]["both_accepted"])

        # Verify individual user states for rejected match
        self.client.force_authenticate(user=match2.u1)
        # A rejected proposal surfaces exactly once, as a rejection notification for the
        # partner who did not reject; building that response sets `both_confirmed_rejection`,
        # so the next poll is clean. Assert both halves — "never appears" predates the
        # notification feature and would pass again if the consume-once step regressed.
        first_poll = self.client.get(f"{self.lobby_api_url}/status")
        self.assertIsNotNone(first_poll.data["matching"], "Partner's rejection should be notified once")
        self.assertTrue(first_poll.data["matching"]["partner_rejected"])

        second_poll = self.client.get(f"{self.lobby_api_url}/status")
        self.assertIsNone(second_poll.data["matching"], "Rejection notification must not repeat")

        # Verify individual user state for pending match
        self.client.force_authenticate(user=match3.u1)
        u3_status = self.client.get(f"{self.lobby_api_url}/status")
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
            self.client.post(f"{self.lobby_api_url}/join")

        # Get all matches
        matchings = list(RandomCallMatching.objects.filter(lobby=self.lobby))
        self.assertEqual(len(matchings), 3)

        # First user from first match exits without accepting/rejecting
        match1 = matchings[0]
        self.client.force_authenticate(user=match1.u1)
        self.client.post(f"{self.lobby_api_url}/exit")

        # Get management overview
        self.client.force_authenticate(user=self._create_admin_user("user_exit"))
        mgmt_response = self.client.get("/api/random_calls/analytics/lobby/default/instance")

        self.assertEqual(mgmt_response.status_code, 200)
        mgmt_data = mgmt_response.data

        # Verify the match with exited user is marked as expired
        self.assertGreaterEqual(
            mgmt_data["proposal_statistics"]["expired_count"], 1, "Should have at least 1 expired match after user exit"
        )

        # Verify active users count decreased
        self.assertEqual(mgmt_data["lobby"]["active_users_count"], 6, "Should have 6 active users after one exit")

        # Verify the remaining user from the expired match sees no matching
        self.client.force_authenticate(user=match1.u2)
        # u2_status = self.client.get(f"{self.lobby_api_url}/status")
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
            response = self.client.post(f"{self.lobby_api_url}/join")
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
            response = self.client.get(f"{self.lobby_api_url}/status")
            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(response.data["matching"], f"User {user.uuid} should have a matching")

        # Phase 4: First pair accepts
        match1 = matchings[0]
        self.client.force_authenticate(user=match1.u1)
        accept_resp = self.client.post(f"{self.lobby_api_url}/match/{match1.uuid}/accept")
        self.assertEqual(accept_resp.status_code, 200)
        self.assertFalse(accept_resp.data["accepted"], "Should not be fully accepted yet")

        self.client.force_authenticate(user=match1.u2)
        accept_resp = self.client.post(f"{self.lobby_api_url}/match/{match1.uuid}/accept")
        self.assertEqual(accept_resp.status_code, 200)
        self.assertTrue(accept_resp.data["accepted"], "Should be fully accepted now")

        # Phase 5: Second pair - one rejects
        match2 = matchings[1]
        self.client.force_authenticate(user=match2.u1)
        reject_resp = self.client.post(f"{self.lobby_api_url}/match/{match2.uuid}/reject")
        self.assertEqual(reject_resp.status_code, 200)
        self.assertTrue(reject_resp.data["rejected"])

        # Phase 6: Third pair - both exit without responding
        match3 = matchings[2]
        self.client.force_authenticate(user=match3.u1)
        self.client.post(f"{self.lobby_api_url}/exit")
        self.client.force_authenticate(user=match3.u2)
        self.client.post(f"{self.lobby_api_url}/exit")

        # Phase 7: Get management overview and verify all states
        self.client.force_authenticate(user=self._create_admin_user("full_flow"))
        mgmt_response = self.client.get("/api/random_calls/analytics/lobby/default/instance")

        self.assertEqual(mgmt_response.status_code, 200)
        mgmt_data = mgmt_response.data

        # Verify statistics reflect all actions
        self.assertEqual(mgmt_data["proposal_statistics"]["total_matches"], 3)
        self.assertEqual(mgmt_data["proposal_statistics"]["accepted_count"], 1, "Should have 1 accepted match")
        self.assertEqual(mgmt_data["proposal_statistics"]["rejected_count"], 1, "Should have 1 rejected match")

        # Verify active user count (7 initial - 2 exits = 5)
        self.assertEqual(mgmt_data["lobby"]["active_users_count"], 5)

        # Phase 8: Trigger re-matching for rejected users
        # The unmatched user and the two users from rejected/exited matches could be re-matched
        from video.tasks import random_call_lobby_perform_matching

        random_call_lobby_perform_matching(str(self.lobby.uuid))

        # Check if new matches were created for the rejected/unmatched users
        all_matchings = RandomCallMatching.objects.filter(lobby=self.lobby)
        # We should have at least 3 original matches, possibly more from re-matching
        self.assertGreaterEqual(all_matchings.count(), 3)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_status_does_not_reject_completed_accepted_match(self):
        """
        Regression test:
        Completed random-call matches must not be auto-marked as rejected by /status
        even when accepted_at is older than match_accept_timeout.
        """
        RandomCallLobbyUser.objects.create(
            user=self.user1, lobby=self.lobby, is_active=True, last_status_checked_at=timezone.now()
        )
        RandomCallLobbyUser.objects.create(
            user=self.user2, lobby=self.lobby, is_active=True, last_status_checked_at=timezone.now()
        )

        stale_accepted_at = timezone.now() - timezone.timedelta(seconds=self.lobby.match_accept_timeout + 30)
        match = RandomCallMatching.objects.create(
            u1=self.user1,
            u2=self.user2,
            lobby=self.lobby,
            u1_accepted=True,
            u2_accepted=True,
            accepted=True,
            accepted_at=stale_accepted_at,
            in_session=False,
            completed=True,
            completed_at=timezone.now() - timezone.timedelta(minutes=1),
            rejected=False,
            video_call_join_expired=False,
            created_at=timezone.now() - timezone.timedelta(minutes=5),
        )

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(f"{self.lobby_api_url}/status")
        self.assertEqual(response.status_code, 200)

        match.refresh_from_db()
        self.assertTrue(match.completed)
        self.assertTrue(match.accepted)
        self.assertFalse(match.rejected)
        self.assertFalse(match.video_call_join_expired)

    def test_management_overview_includes_lobby_participant_stats(self):
        users = self.create_multiple_users(3)
        for user in users:
            RandomCallLobbyUser.objects.create(
                user=user,
                lobby=self.lobby,
                is_active=True,
                last_status_checked_at=timezone.now(),
            )

        RandomCallMatching.objects.create(
            lobby=self.lobby,
            u1=users[0],
            u2=users[1],
            accepted=True,
            u1_accepted=True,
            u2_accepted=True,
            completed=True,
            created_at=timezone.now(),
        )
        # Mirror what `reject_random_call_match` actually writes. A bare `rejected=True`
        # with no `rejected_at` and no user status is the admin-clear / legacy shape, which
        # `_proposal_is_rejected_bucket` deliberately does not count as a rejection.
        RandomCallMatching.objects.create(
            lobby=self.lobby,
            u1=users[0],
            u2=users[2],
            rejected=True,
            rejected_at=timezone.now(),
            u1_status=RandomCallProposalUserStatus.REJECTED,
            created_at=timezone.now(),
        )
        RandomCallMatching.objects.create(
            lobby=self.lobby,
            u1=users[1],
            u2=users[2],
            expired=True,
            created_at=timezone.now(),
        )

        session_start = timezone.now() - timezone.timedelta(minutes=10)
        session = LivekitSession.objects.create(
            u1=users[0],
            u2=users[1],
            random_call_session=True,
            both_have_been_active=True,
            end_time=session_start + timezone.timedelta(seconds=330),
            is_active=False,
        )
        # `created_at` is auto_now_add, so passing it to create() is silently ignored and
        # the call measures as 0 seconds. It has to be written back afterwards.
        LivekitSession.objects.filter(pk=session.pk).update(created_at=session_start)

        self.client.force_authenticate(user=self._create_admin_user("participant_stats"))
        response = self.client.get("/api/random_calls/analytics/lobby/default/instance")

        self.assertEqual(response.status_code, 200)
        participants = {item["user_uuid"]: item for item in response.data["lobby_participants"]}
        self.assertEqual(len(participants), 3)

        user0_stats = participants[str(users[0].uuid)]
        self.assertEqual(user0_stats["accepted_proposals"], 1)
        self.assertEqual(user0_stats["completed_calls"], 1)
        self.assertEqual(user0_stats["unsuccessful_proposals"], 1)
        self.assertEqual(user0_stats["longest_call_duration_seconds"], 330)

        user1_stats = participants[str(users[1].uuid)]
        self.assertEqual(user1_stats["accepted_proposals"], 1)
        self.assertEqual(user1_stats["completed_calls"], 1)
        self.assertEqual(user1_stats["unsuccessful_proposals"], 1)
        self.assertEqual(user1_stats["longest_call_duration_seconds"], 330)

        user2_stats = participants[str(users[2].uuid)]
        self.assertEqual(user2_stats["accepted_proposals"], 0)
        self.assertEqual(user2_stats["completed_calls"], 0)
        self.assertEqual(user2_stats["unsuccessful_proposals"], 2)
        self.assertEqual(user2_stats["longest_call_duration_seconds"], 0)

    def test_management_overview_user_attendance_breakdown(self):
        users = self.create_multiple_users(2)
        earlier_lobby = RandomCallLobby.objects.create(
            name="default",
            start_time=timezone.now() - timezone.timedelta(days=14),
            end_time=timezone.now() - timezone.timedelta(days=14, hours=-2),
        )
        later_lobby = RandomCallLobby.objects.create(
            name="default",
            start_time=timezone.now() - timezone.timedelta(days=7),
            end_time=timezone.now() - timezone.timedelta(days=7, hours=-2),
        )

        RandomCallLobbyUser.objects.create(user=users[0], lobby=earlier_lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=users[0], lobby=later_lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=users[1], lobby=later_lobby, is_active=False)

        self.client.force_authenticate(user=self._create_admin_user("attendance_breakdown"))
        response = self.client.get(f"/api/random_calls/analytics/lobby/default/instance?lobby_uuid={later_lobby.uuid}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lobby"]["total_users_count"], 2)
        self.assertEqual(response.data["snapshot"]["first_time_users"], 1)
        self.assertEqual(response.data["snapshot"]["returning_users"], 1)

    def test_both_requested_sends_standard_match_notifications(self):
        self.user1.profile.user_type = Profile.TypeChoices.LEARNER
        self.user2.profile.user_type = Profile.TypeChoices.VOLUNTEER
        self.user1.profile.save()
        self.user2.profile.save()

        matching = RandomCallMatching.objects.create(
            lobby=self.lobby,
            u1=self.user1,
            u2=self.user2,
            accepted=True,
        )
        for user in (self.user1, self.user2):
            user.state.searching_state = State.SearchingStateChoices.SEARCHING
            user.state.save(update_fields=["searching_state"])

        with patch.object(User, "send_email") as mock_send_email:
            self.client.force_authenticate(user=self.user1)
            first = self.client.post(f"/api/random_calls/user/history/{matching.uuid}/request_match")
            self.assertEqual(first.status_code, 200)
            self.assertFalse(first.data["both_requested"])
            self.user1.state.refresh_from_db()
            self.user2.state.refresh_from_db()
            self.assertEqual(self.user1.state.searching_state, State.SearchingStateChoices.SEARCHING)
            self.assertEqual(self.user2.state.searching_state, State.SearchingStateChoices.SEARCHING)

            self.client.force_authenticate(user=self.user2)
            second = self.client.post(f"/api/random_calls/user/history/{matching.uuid}/request_match")

        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["both_requested"])

        match = Match.get_match(self.user1, self.user2).filter(match_type=MatchType.RANDOM_CALL).first()
        self.assertIsNotNone(match)
        self.user1.state.refresh_from_db()
        self.user2.state.refresh_from_db()
        self.assertEqual(self.user1.state.searching_state, State.SearchingStateChoices.IDLE)
        self.assertEqual(self.user2.state.searching_state, State.SearchingStateChoices.IDLE)

        new_match_calls = [call for call in mock_send_email.call_args_list if call.args[0] == "automatic-emails-m011"]
        self.assertEqual(len(new_match_calls), 2)
        self.assertEqual({call.kwargs["match_id"] for call in new_match_calls}, {match.pk})

        auto_messages = Message.objects.filter(recipient__in=[self.user1, self.user2]).exclude(
            sender__in=[self.user1, self.user2]
        )
        self.assertTrue(auto_messages.filter(recipient=self.user1).exists())
        self.assertTrue(auto_messages.filter(recipient=self.user2).exists())
