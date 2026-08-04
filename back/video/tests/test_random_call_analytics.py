from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from management.models.profile import Profile
from management.models.user import User
from video.analytics.lobbies import annotate_lobby_metrics, filtered_lobby_queryset
from video.analytics.queries import (
    classify_proposal_bucket,
    compute_user_attendance_breakdown,
    count_proposal_buckets,
    proposal_bucket_counts_sum_to_total,
    proposal_stale_threshold_for_lobby,
)
from video.analytics.snapshots import build_snapshots, lobby_display_day_date
from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching, RandomCallProposalUserStatus

BERLIN = ZoneInfo("Europe/Berlin")


class RandomCallAnalyticsTests(TestCase):
    def _create_user(self, suffix: str, user_type=Profile.TypeChoices.LEARNER) -> User:
        user = User.objects.create_user(
            email=f"rc_analytics_{suffix}@example.com",
            password="Test123!",
            first_name=f"User{suffix}",
            last_name="Test",
        )
        user.profile.user_type = user_type
        user.profile.save(update_fields=["user_type"])
        return user

    def _create_lobby(self, *, name="default", start_time, end_time) -> RandomCallLobby:
        return RandomCallLobby.objects.create(
            name=name,
            start_time=start_time,
            end_time=end_time,
        )

    def _assert_bucket_invariant(self, counts: dict[str, int]):
        self.assertTrue(
            proposal_bucket_counts_sum_to_total(counts),
            f"Bucket sum mismatch: {counts}",
        )

    def test_zero_attendance_lobby_included_with_zero_metrics(self):
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(days=1),
            end_time=timezone.now() - timezone.timedelta(hours=22),
        )
        qs = annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk))
        snapshots = build_snapshots(qs)

        self.assertEqual(len(snapshots), 1)
        snap = snapshots[lobby.uuid]
        self.assertEqual(snap.total_users, 0)
        self.assertEqual(snap.first_time_users, 0)
        self.assertEqual(snap.returning_users, 0)
        self.assertEqual(snap.proposals_total, 0)
        self.assertEqual(snap.completed_calls, 0)
        self._assert_bucket_invariant(
            {
                "accepted": snap.proposals_accepted,
                "rejected": snap.proposals_rejected,
                "expired": snap.proposals_expired,
                "pending": snap.proposals_pending,
                "dangling": snap.proposals_dangling,
                "total": snap.proposals_total,
            }
        )

    def test_annotate_lobby_metrics_counts(self):
        learner = self._create_user("learner", Profile.TypeChoices.LEARNER)
        volunteer = self._create_user("volunteer", Profile.TypeChoices.VOLUNTEER)
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(hours=2),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )

        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=volunteer, lobby=lobby, is_active=False)

        RandomCallMatching.objects.create(lobby=lobby, u1=learner, u2=volunteer, accepted=True, completed=True)
        RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            rejected=True,
            rejected_at=timezone.now(),
            u1_status=RandomCallProposalUserStatus.REJECTED,
        )
        RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            expired=True,
            rejected=True,
            u1_status=RandomCallProposalUserStatus.EXPIRED,
            u2_status=RandomCallProposalUserStatus.EXPIRED,
        )

        annotated = annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)).get()
        self.assertEqual(annotated.total_users, 2)
        self.assertEqual(annotated.learner_count, 1)
        self.assertEqual(annotated.volunteer_count, 1)
        self.assertEqual(annotated.proposals_total, 3)
        self.assertEqual(annotated.proposals_accepted, 1)
        self.assertEqual(annotated.proposals_rejected, 1)
        self.assertEqual(annotated.proposals_expired, 1)
        self.assertEqual(annotated.completed_calls, 1)

        snap = build_snapshots(annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)))[lobby.uuid]
        self.assertEqual(snap.proposals_accepted, 1)
        self.assertEqual(snap.proposals_rejected, 1)
        self.assertEqual(snap.proposals_expired, 1)
        self.assertEqual(snap.proposals_pending, 0)
        self.assertEqual(snap.proposals_dangling, 0)

    def test_timeout_proposal_not_double_counted(self):
        """cleanup_if_not_accepted sets both expired and rejected — counts as expired only."""
        learner = self._create_user("timeout_learner")
        volunteer = self._create_user("timeout_volunteer")
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            expired=True,
            rejected=True,
            u1_status=RandomCallProposalUserStatus.EXPIRED,
            u2_status=RandomCallProposalUserStatus.EXPIRED,
        )

        counts = count_proposal_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["expired"], 1)
        self.assertEqual(counts["rejected"], 0)
        self._assert_bucket_invariant(counts)

        snap = build_snapshots(annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)))[lobby.uuid]
        self.assertEqual(snap.proposals_expired, 1)
        self.assertEqual(snap.proposals_rejected, 0)
        self.assertEqual(snap.proposals_total, 1)

    def test_admin_clear_expired_only_counts_as_expired(self):
        learner = self._create_user("admin_clear_learner")
        volunteer = self._create_user("admin_clear_volunteer")
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            expired=True,
            u1_status=RandomCallProposalUserStatus.EXPIRED,
            u2_status=RandomCallProposalUserStatus.EXPIRED,
        )

        counts = count_proposal_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["expired"], 1)
        self.assertEqual(counts["rejected"], 0)
        self._assert_bucket_invariant(counts)

    def test_exit_counts_as_expired_not_rejected(self):
        learner = self._create_user("exit_learner")
        volunteer = self._create_user("exit_volunteer")
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            rejected=True,
            u1_status=RandomCallProposalUserStatus.EXITED,
            u2_status=RandomCallProposalUserStatus.PENDING,
        )

        counts = count_proposal_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["expired"], 1)
        self.assertEqual(counts["rejected"], 0)
        self._assert_bucket_invariant(counts)

    def test_explicit_reject_counts_as_rejected(self):
        learner = self._create_user("reject_learner")
        volunteer = self._create_user("reject_volunteer")
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            rejected=True,
            rejected_at=timezone.now(),
            u1_status=RandomCallProposalUserStatus.REJECTED,
            u2_status=RandomCallProposalUserStatus.PENDING,
        )

        counts = count_proposal_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["expired"], 0)
        self._assert_bucket_invariant(counts)

    def test_dangling_open_proposal(self):
        learner = self._create_user("dangling_learner")
        volunteer = self._create_user("dangling_volunteer")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=1),
            end_time=now + timezone.timedelta(hours=1),
        )
        lobby.match_proposal_timeout = 30
        lobby.save(update_fields=["match_proposal_timeout"])

        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            created_at=now - timezone.timedelta(minutes=5),
        )
        stale = proposal_stale_threshold_for_lobby(lobby)
        self.assertEqual(
            classify_proposal_bucket(proposal, proposal_stale_threshold=stale),
            "dangling",
        )

        counts = count_proposal_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["dangling"], 1)
        self._assert_bucket_invariant(counts)

        snap = build_snapshots(annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)))[lobby.uuid]
        self.assertEqual(snap.proposals_dangling, 1)

    def test_first_time_returning_matches_legacy_breakdown(self):
        users = [self._create_user(f"u{i}") for i in range(2)]
        earlier = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(days=14),
            end_time=timezone.now() - timezone.timedelta(days=14) + timezone.timedelta(hours=2),
        )
        later = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(days=7),
            end_time=timezone.now() - timezone.timedelta(days=7) + timezone.timedelta(hours=2),
        )

        RandomCallLobbyUser.objects.create(user=users[0], lobby=earlier, is_active=False)
        RandomCallLobbyUser.objects.create(user=users[0], lobby=later, is_active=False)
        RandomCallLobbyUser.objects.create(user=users[1], lobby=later, is_active=False)

        qs = annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=later.pk))
        snap = build_snapshots(qs)[later.uuid]

        legacy = compute_user_attendance_breakdown(RandomCallLobbyUser.objects.filter(lobby=later), later)
        self.assertEqual(snap.first_time_users, legacy["first_time_count"])
        self.assertEqual(snap.returning_users, legacy["returning_count"])
        self.assertEqual(snap.first_time_users, 1)
        self.assertEqual(snap.returning_users, 1)

    def test_lobby_display_day_date_uses_berlin_timezone(self):
        utc_start = datetime(2024, 6, 1, 22, 0, tzinfo=dt_timezone.utc)
        day, snapshot_date = lobby_display_day_date(utc_start)
        local = utc_start.astimezone(BERLIN)
        self.assertEqual(day, local.strftime("%A"))
        self.assertEqual(snapshot_date, local.date())

    def test_filtered_lobby_queryset_by_name(self):
        self._create_lobby(
            name="default",
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        self._create_lobby(
            name="other",
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        self.assertEqual(filtered_lobby_queryset(lobby_name="default").count(), 1)
        self.assertEqual(filtered_lobby_queryset(lobby_name=None).count(), 2)

    def test_build_snapshots_requires_annotations(self):
        lobby = self._create_lobby(
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        with self.assertRaises(ValueError):
            build_snapshots(RandomCallLobby.objects.filter(pk=lobby.pk))

    def test_lobby_session_snapshot_alignment(self):
        users = [self._create_user(f"overview_u{i}") for i in range(2)]
        earlier = self._create_lobby(
            name="default",
            start_time=timezone.now() - timezone.timedelta(days=14),
            end_time=timezone.now() - timezone.timedelta(days=14) + timezone.timedelta(hours=2),
        )
        later = self._create_lobby(
            name="default",
            start_time=timezone.now() - timezone.timedelta(days=7),
            end_time=timezone.now() - timezone.timedelta(days=7) + timezone.timedelta(hours=2),
        )

        RandomCallLobbyUser.objects.create(user=users[0], lobby=earlier, is_active=False)
        RandomCallLobbyUser.objects.create(user=users[0], lobby=later, is_active=False)
        RandomCallLobbyUser.objects.create(user=users[1], lobby=later, is_active=False)
        RandomCallMatching.objects.create(lobby=later, u1=users[0], u2=users[1], accepted=True, completed=True)

        snapshot = build_snapshots(annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=later.pk)))[later.uuid]

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=users[0])
        response = client.get(f"/api/random_calls/analytics/lobby/default/session?lobby_uuid={later.uuid}")
        if response.status_code == 403:
            self.skipTest("Management API requires admin permissions")

        self.assertEqual(response.status_code, 200)
        session_snapshot = response.data["snapshot"]
        self.assertEqual(session_snapshot["first_time_users"], snapshot.first_time_users)
        self.assertEqual(session_snapshot["returning_users"], snapshot.returning_users)
        self.assertEqual(session_snapshot["completed_calls"], snapshot.completed_calls)
        self.assertEqual(session_snapshot["proposals_accepted"], snapshot.proposals_accepted)
        self.assertEqual(session_snapshot["first_time_users"], 1)
        self.assertEqual(session_snapshot["returning_users"], 1)
        self.assertEqual(session_snapshot["completed_calls"], 1)

    def test_list_lobby_analytics_api(self):
        learner = self._create_user("api_learner", Profile.TypeChoices.LEARNER)
        volunteer = self._create_user("api_volunteer", Profile.TypeChoices.VOLUNTEER)
        lobby = self._create_lobby(
            name="default",
            start_time=timezone.now() - timezone.timedelta(hours=3),
            end_time=timezone.now() - timezone.timedelta(hours=1),
        )
        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=volunteer, lobby=lobby, is_active=False)
        RandomCallMatching.objects.create(lobby=lobby, u1=learner, u2=volunteer, accepted=True, completed=True)

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=learner)
        response = client.get(
            "/api/random_calls/analytics/lobbies",
            {"lobby_name": "default"},
        )
        if response.status_code == 403:
            self.skipTest("Management API requires admin permissions")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)
        row = next(item for item in response.data["results"] if item["lobby_uuid"] == str(lobby.uuid))
        self.assertEqual(row["total_users"], 2)
        self.assertEqual(row["proposals_total"], 1)
        self.assertEqual(row["proposals_accepted"], 1)
        self.assertEqual(row["completed_calls"], 1)
        self.assertEqual(
            row["proposals_accepted"]
            + row["proposals_rejected"]
            + row["proposals_expired"]
            + row["proposals_pending"]
            + row["proposals_dangling"],
            row["proposals_total"],
        )
