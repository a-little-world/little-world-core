from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from management.models.profile import Profile
from management.models.user import User
from video.analytics.display_time import parse_analytics_datetime_bound
from video.analytics.instance_detail import build_lobby_instance_detail
from video.analytics.lobbies import annotate_lobby_metrics, apply_lobby_ordering, filtered_lobby_queryset
from video.analytics.queries import (
    PROPOSAL_BUCKET_FIELDS,
    build_completed_call_durations,
    build_lobby_participants,
    classify_proposal_bucket,
    compute_user_attendance_breakdown,
    proposal_stale_threshold_for_lobby,
)
from video.analytics.snapshots import (
    assert_sql_python_proposal_buckets_strict,
    build_snapshots,
    lobby_display_day_date,
    lobby_instance_snapshot_to_dict,
)
from video.livekit_webhook import _matching_for_completed_random_call
from video.lobby_resolution import InvalidLobbyUuid, resolve_lobby_instance
from video.models import (
    LivekitSession,
    RandomCallLobby,
    RandomCallLobbyUser,
    RandomCallMatching,
    RandomCallProposalUserStatus,
)
from video.random_calls import is_lobby_active

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

    def _create_admin_user(self, suffix: str = "admin") -> User:
        """A user that is genuinely staff, so `IsAdminOrMatchingUser` lets them in.

        `UserManager.create_user` hard-sets `kwargs["is_staff"] = False`, so passing
        `is_staff=True` to it was silently discarded and every API test in this class
        returned 403. Set it with a follow-up write, the same way `auto_now_add` fields
        have to be. `create_superuser` would work too but grants more than these tests
        need — and expects `second_name` rather than `last_name`.
        """
        user = User.objects.create_user(
            email=f"rc_admin_{suffix}@example.com",
            password="Test123!",
            first_name=f"Admin{suffix}",
            last_name="Test",
        )
        User.objects.filter(pk=user.pk).update(is_staff=True)
        user.refresh_from_db()
        assert user.is_staff, "admin fixture must be staff or every endpoint test 403s"
        return user

    def _create_livekit_session(self, **kwargs) -> LivekitSession:
        created_at = kwargs.pop("created_at", None)
        session = LivekitSession.objects.create(**kwargs)
        if created_at is not None:
            LivekitSession.objects.filter(pk=session.pk).update(created_at=created_at)
            session.refresh_from_db()
        return session

    def _classify_all_buckets(self, proposals, lobby, *, active_lobby_user_ids=None, as_of=None):
        stale = proposal_stale_threshold_for_lobby(lobby, as_of=as_of)
        counts = {bucket: 0 for bucket in PROPOSAL_BUCKET_FIELDS}
        for proposal in proposals:
            bucket = classify_proposal_bucket(
                proposal,
                active_lobby_user_ids=active_lobby_user_ids,
                proposal_stale_threshold=stale,
            )
            counts[bucket] += 1
        counts["total"] = len(proposals)
        return counts

    def _assert_classifier_bucket_invariant(self, counts: dict[str, int]):
        self.assertEqual(sum(counts[bucket] for bucket in PROPOSAL_BUCKET_FIELDS), counts["total"])

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
        self._assert_classifier_bucket_invariant(
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

        # Legacy orphan row (completed without accepted) buckets into SQL expired.
        RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            completed=True,
            accepted=False,
        )
        annotated_after = annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)).get()
        self.assertEqual(annotated_after.proposals_total, 4)
        self.assertEqual(annotated_after.proposals_expired, 2)
        self.assertEqual(annotated_after.completed_calls, 1)

        snap_after = build_snapshots(annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)))[lobby.uuid]
        self.assertEqual(snap_after.bucket_mismatch, 0)
        assert_sql_python_proposal_buckets_strict(
            annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)).get(),
            open_buckets={"pending": snap_after.proposals_pending, "dangling": snap_after.proposals_dangling},
        )

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

        counts = self._classify_all_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["expired"], 1)
        self.assertEqual(counts["rejected"], 0)
        self._assert_classifier_bucket_invariant(counts)

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

        counts = self._classify_all_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["expired"], 1)
        self.assertEqual(counts["rejected"], 0)
        self._assert_classifier_bucket_invariant(counts)

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

        counts = self._classify_all_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["expired"], 1)
        self.assertEqual(counts["rejected"], 0)
        self._assert_classifier_bucket_invariant(counts)

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

        counts = self._classify_all_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["expired"], 0)
        self._assert_classifier_bucket_invariant(counts)

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

        counts = self._classify_all_buckets([proposal], lobby=lobby)
        self.assertEqual(counts["dangling"], 1)
        self._assert_classifier_bucket_invariant(counts)

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

    def test_lobby_instance_snapshot_alignment(self):
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
        client.force_authenticate(user=self._create_admin_user("alignment"))
        response = client.get(f"/api/random_calls/analytics/lobby/default/instance?lobby_uuid={later.uuid}")

        self.assertEqual(response.status_code, 200)
        instance_snapshot = response.data["snapshot"]
        self.assertEqual(instance_snapshot["first_time_users"], snapshot.first_time_users)
        self.assertEqual(instance_snapshot["returning_users"], snapshot.returning_users)
        self.assertEqual(instance_snapshot["completed_calls"], snapshot.completed_calls)
        self.assertEqual(instance_snapshot["proposals_accepted"], snapshot.proposals_accepted)
        self.assertEqual(instance_snapshot["first_time_users"], 1)
        self.assertEqual(instance_snapshot["returning_users"], 1)
        self.assertEqual(instance_snapshot["completed_calls"], 1)

    def test_finished_lobby_list_and_detail_snapshots_match(self):
        """Finished lobbies must not reclassify open proposals using inactive-user heuristics."""
        learner = self._create_user("finished_learner")
        volunteer = self._create_user("finished_volunteer")
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(days=3),
            end_time=timezone.now() - timezone.timedelta(days=3) + timezone.timedelta(hours=2),
        )
        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=volunteer, lobby=lobby, is_active=False)
        RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            created_at=lobby.start_time + timezone.timedelta(minutes=10),
        )

        list_snapshot = lobby_instance_snapshot_to_dict(
            build_snapshots(annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)))[lobby.uuid]
        )
        detail = build_lobby_instance_detail(lobby)
        self.assertEqual(detail["snapshot"], list_snapshot)
        self.assertEqual(list_snapshot["proposals_dangling"], 1)
        self.assertEqual(list_snapshot["bucket_mismatch"], 0)
        stats = detail["proposal_statistics"]
        self.assertEqual(stats["dangling_count"], len(detail["match_proposals"]["dangling"]))
        self.assertEqual(stats["expired_count"], len(detail["match_proposals"]["expired"]))

    def test_completed_call_duration_scoped_to_lobby_and_proposal(self):
        learner = self._create_user("duration_learner")
        volunteer = self._create_user("duration_volunteer")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=30),
        )
        accepted_at = now - timezone.timedelta(hours=1, minutes=30)
        completed_at = now - timezone.timedelta(hours=1)
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=accepted_at,
            completed_at=completed_at,
        )
        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=volunteer, lobby=lobby, is_active=False)

        # Old call between the same pair — must not affect this lobby's stats.
        old_start = now - timezone.timedelta(days=21)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=old_start,
            end_time=old_start + timezone.timedelta(seconds=9999),
            is_active=False,
        )

        in_lobby_start = accepted_at + timezone.timedelta(minutes=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=in_lobby_start,
            end_time=in_lobby_start + timezone.timedelta(seconds=240),
            is_active=False,
        )

        durations = build_completed_call_durations([proposal], lobby=lobby)
        self.assertEqual(durations[proposal.pk], 240)

        participants = build_lobby_participants(
            RandomCallLobbyUser.objects.filter(lobby=lobby),
            [proposal],
            lobby,
            set(),
            as_of=now,
        )
        learner_row = next(row for row in participants if row["user_id"] == learner.pk)
        self.assertEqual(learner_row["longest_call_duration_seconds"], 240)

    def test_call_duration_includes_time_after_lobby_end(self):
        """A call may start before lobby.end_time and finish after it — duration is not capped at lobby end."""
        learner = self._create_user("late_call_learner")
        volunteer = self._create_user("late_call_volunteer")
        lobby_end = timezone.now() - timezone.timedelta(minutes=45)
        lobby = self._create_lobby(
            start_time=lobby_end - timezone.timedelta(hours=2),
            end_time=lobby_end,
        )
        accepted_at = lobby_end - timezone.timedelta(minutes=10)
        completed_at = lobby_end + timezone.timedelta(minutes=20)
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=accepted_at,
            completed_at=completed_at,
        )

        session_start = lobby_end - timezone.timedelta(minutes=8)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=session_start,
            end_time=session_start + timezone.timedelta(minutes=28),
            is_active=False,
        )

        durations = build_completed_call_durations([proposal], lobby=lobby)
        self.assertEqual(durations[proposal.pk], 28 * 60)

    def test_dropped_call_counts_both_legs(self):
        """A short leg near acceptance plus a long one is a single conversation.

        Previously this took the longest session, which stopped a 3-minute reconnect
        *hiding* a 52-minute call but silently threw the 3 minutes away. Summing keeps
        both — the window already guarantees they belong to this proposal.
        """
        learner = self._create_user("reconnect_learner")
        volunteer = self._create_user("reconnect_volunteer")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=30),
        )
        accepted_at = now - timezone.timedelta(hours=1, minutes=30)
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=accepted_at,
            completed_at=accepted_at + timezone.timedelta(minutes=55),
        )
        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=volunteer, lobby=lobby, is_active=False)

        short_start = accepted_at + timezone.timedelta(seconds=30)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=short_start,
            end_time=short_start + timezone.timedelta(seconds=209),  # 0h 3m 29s
            is_active=False,
        )
        long_start = accepted_at + timezone.timedelta(minutes=5)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=long_start,
            end_time=long_start + timezone.timedelta(minutes=52),
            is_active=False,
        )

        durations = build_completed_call_durations([proposal], lobby=lobby)
        self.assertEqual(durations[proposal.pk], 52 * 60 + 209)

        participants = build_lobby_participants(
            RandomCallLobbyUser.objects.filter(lobby=lobby),
            [proposal],
            lobby,
            set(),
            as_of=now,
        )
        learner_row = next(row for row in participants if row["user_id"] == learner.pk)
        # The proposal's duration is both legs, so the participant's longest call is too.
        self.assertEqual(learner_row["longest_call_duration_seconds"], 52 * 60 + 209)
        self.assertEqual(learner_row["completed_calls"], 1)

    def test_longest_call_across_multiple_partners_uses_max(self):
        learner = self._create_user("multi_partner_learner")
        volunteer_a = self._create_user("multi_partner_a")
        volunteer_b = self._create_user("multi_partner_b")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=30),
        )
        first_accepted = now - timezone.timedelta(hours=1, minutes=40)
        second_accepted = now - timezone.timedelta(hours=1)
        proposal_a = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer_a,
            accepted=True,
            completed=True,
            accepted_at=first_accepted,
            completed_at=first_accepted + timezone.timedelta(minutes=10),
        )
        proposal_b = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer_b,
            accepted=True,
            completed=True,
            accepted_at=second_accepted,
            completed_at=second_accepted + timezone.timedelta(minutes=55),
        )
        for user in (learner, volunteer_a, volunteer_b):
            RandomCallLobbyUser.objects.create(user=user, lobby=lobby, is_active=False)

        short_start = first_accepted + timezone.timedelta(minutes=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer_a,
            random_call_session=True,
            both_have_been_active=True,
            created_at=short_start,
            end_time=short_start + timezone.timedelta(seconds=209),
            is_active=False,
        )
        long_start = second_accepted + timezone.timedelta(minutes=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer_b,
            random_call_session=True,
            both_have_been_active=True,
            created_at=long_start,
            end_time=long_start + timezone.timedelta(minutes=52),
            is_active=False,
        )

        participants = build_lobby_participants(
            RandomCallLobbyUser.objects.filter(lobby=lobby),
            [proposal_a, proposal_b],
            lobby,
            set(),
            as_of=now,
        )
        learner_row = next(row for row in participants if row["user_id"] == learner.pk)
        self.assertEqual(learner_row["completed_calls"], 2)
        self.assertEqual(learner_row["longest_call_duration_seconds"], 52 * 60)

    def test_reconnected_call_sums_its_sessions(self):
        """A drop-and-reconnect is one conversation split across rows.

        Taking only the longest leg silently discarded the rest — a 3-minute call that
        dropped and resumed for 20 reported 20, not 23.
        """
        learner = self._create_user("reconnect_learner")
        volunteer = self._create_user("reconnect_volunteer")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=30),
        )
        accepted = now - timezone.timedelta(hours=1, minutes=40)
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=accepted,
            completed_at=accepted + timezone.timedelta(minutes=30),
        )
        first = accepted + timezone.timedelta(minutes=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=first,
            end_time=first + timezone.timedelta(minutes=3),
            is_active=False,
        )
        second = accepted + timezone.timedelta(minutes=5)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=second,
            end_time=second + timezone.timedelta(minutes=20),
            is_active=False,
        )

        durations = build_completed_call_durations([proposal], lobby=lobby)
        self.assertEqual(durations[proposal.pk], 23 * 60)

    def test_sole_proposal_without_accepted_at_still_gets_its_duration(self):
        """`accepted_at` is NULL on every row predating migration video.0024.

        The sort key used to build a sentinel from ``django.utils.timezone.utc``, which
        Django 5 removed — the whole lobby detail endpoint raised AttributeError. Beyond
        the crash, these rows should still be measurable: with only one proposal for the
        pair the lobby window identifies the call on its own, so nothing is ambiguous.
        """
        learner = self._create_user("no_accepted_at_learner")
        volunteer = self._create_user("no_accepted_at_volunteer")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=30),
        )
        proposal = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=None,
        )
        start = now - timezone.timedelta(hours=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=start,
            end_time=start + timezone.timedelta(minutes=12),
            is_active=False,
        )

        durations = build_completed_call_durations([proposal], lobby=lobby)
        self.assertEqual(durations[proposal.pk], 12 * 60)

    def test_two_proposals_without_accepted_at_do_not_share_one_session(self):
        """Both fell back to the whole-lobby window and each claimed the same call.

        With a second proposal for the pair there is no way to tell which call belongs to
        which, so neither is attributed — better than counting one call twice.
        """
        learner = self._create_user("dup_learner")
        volunteer = self._create_user("dup_volunteer")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=30),
        )
        proposal_1 = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=None,
        )
        proposal_2 = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=None,
        )
        start = now - timezone.timedelta(hours=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=start,
            end_time=start + timezone.timedelta(minutes=18),
            is_active=False,
        )

        durations = build_completed_call_durations([proposal_1, proposal_2], lobby=lobby)
        self.assertEqual(durations[proposal_1.pk], 0)
        self.assertEqual(durations[proposal_2.pk], 0)
        self.assertEqual(sum(durations.values()), 0, "one call must not be counted twice")

    def test_unaccepted_proposal_does_not_bound_an_accepted_one(self):
        """An unaccepted proposal sorts first but carries no time, so it closes no window."""
        learner = self._create_user("mixed_learner")
        volunteer = self._create_user("mixed_volunteer")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=30),
        )
        accepted = now - timezone.timedelta(hours=1, minutes=40)
        unaccepted = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=None,
        )
        real = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=accepted,
            completed_at=accepted + timezone.timedelta(minutes=20),
        )
        start = accepted + timezone.timedelta(minutes=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=start,
            end_time=start + timezone.timedelta(minutes=17),
            is_active=False,
        )

        durations = build_completed_call_durations([unaccepted, real], lobby=lobby)
        self.assertEqual(durations[unaccepted.pk], 0)
        self.assertEqual(durations[real.pk], 17 * 60)

    def test_same_pair_rematch_keeps_each_proposal_duration(self):
        learner = self._create_user("rematch_learner")
        volunteer = self._create_user("rematch_volunteer")
        now = timezone.now()
        lobby = self._create_lobby(
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=30),
        )
        first_accepted = now - timezone.timedelta(hours=1, minutes=40)
        second_accepted = now - timezone.timedelta(hours=1)
        proposal_1 = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=first_accepted,
            completed_at=first_accepted + timezone.timedelta(minutes=20),
        )
        proposal_2 = RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=True,
            accepted_at=second_accepted,
            completed_at=second_accepted + timezone.timedelta(minutes=55),
        )
        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=volunteer, lobby=lobby, is_active=False)

        first_start = first_accepted + timezone.timedelta(minutes=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=first_start,
            end_time=first_start + timezone.timedelta(minutes=15),
            is_active=False,
        )
        second_start = second_accepted + timezone.timedelta(minutes=1)
        self._create_livekit_session(
            u1=learner,
            u2=volunteer,
            random_call_session=True,
            both_have_been_active=True,
            created_at=second_start,
            end_time=second_start + timezone.timedelta(minutes=52),
            is_active=False,
        )

        durations = build_completed_call_durations([proposal_1, proposal_2], lobby=lobby)
        self.assertEqual(durations[proposal_1.pk], 15 * 60)
        self.assertEqual(durations[proposal_2.pk], 52 * 60)

        participants = build_lobby_participants(
            RandomCallLobbyUser.objects.filter(lobby=lobby),
            [proposal_1, proposal_2],
            lobby,
            set(),
            as_of=now,
        )
        learner_row = next(row for row in participants if row["user_id"] == learner.pk)
        self.assertEqual(learner_row["completed_calls"], 2)
        self.assertEqual(learner_row["longest_call_duration_seconds"], 52 * 60)

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
        client.force_authenticate(user=self._create_admin_user("list_api"))
        response = client.get(
            "/api/random_calls/analytics/lobbies",
            {"lobby_name": "default"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)
        row = next(item for item in response.data["results"] if item["lobby_uuid"] == str(lobby.uuid))
        self.assertEqual(row["total_users"], 2)
        self.assertEqual(row["proposals_total"], 1)
        self.assertEqual(row["proposals_accepted"], 1)
        self.assertEqual(row["completed_calls"], 1)
        self.assertTrue(row["proposals_are_final"])
        self.assertEqual(
            row["proposals_accepted"]
            + row["proposals_rejected"]
            + row["proposals_expired"]
            + row["proposals_pending"]
            + row["proposals_dangling"],
            row["proposals_total"],
        )

    def test_list_lobby_analytics_proposals_are_final_flag(self):
        live_lobby = self._create_lobby(
            name="default",
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        finished_lobby = self._create_lobby(
            name="default",
            start_time=timezone.now() - timezone.timedelta(hours=3),
            end_time=timezone.now() - timezone.timedelta(hours=1),
        )

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self._create_admin_user("list_proposals_final"))
        response = client.get("/api/random_calls/analytics/lobbies", {"lobby_name": "default"})

        self.assertEqual(response.status_code, 200)
        rows = {item["lobby_uuid"]: item for item in response.data["results"]}
        self.assertFalse(rows[str(live_lobby.uuid)]["proposals_are_final"])
        self.assertTrue(rows[str(finished_lobby.uuid)]["proposals_are_final"])

    def test_resolve_lobby_instance_requires_matching_name_for_uuid(self):
        now = timezone.now()
        lobby = self._create_lobby(
            name="default",
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(hours=1),
        )
        self.assertIsNone(resolve_lobby_instance("other", lobby_uuid=str(lobby.uuid)))
        self.assertEqual(resolve_lobby_instance("default", lobby_uuid=str(lobby.uuid)), lobby)

    def test_end_of_day_bound_is_the_last_microsecond_not_midnight(self):
        """`end_of_day` was silently ignored for date-only input — the only input it serves.

        `parse_datetime` has accepted date-only strings since Django 4.1, returning
        midnight, so it claimed the value before the end_of_day branch ran. Combined with
        `start_time__lte=to_dt`, `from=X&to=X` matched only lobbies starting at exactly
        00:00:00 — a same-day filter returned nothing.
        """
        bound = parse_analytics_datetime_bound("2026-01-01", end_of_day=True)
        self.assertEqual(bound.tzinfo, BERLIN)
        self.assertEqual((bound.hour, bound.minute, bound.second), (23, 59, 59))
        self.assertEqual(bound.microsecond, 999999)

        # A value carrying a time is still honoured verbatim, aware or naive.
        self.assertEqual(
            parse_analytics_datetime_bound("2026-01-01T10:00:00", end_of_day=True),
            datetime(2026, 1, 1, 10, 0, tzinfo=BERLIN),
        )
        self.assertEqual(
            parse_analytics_datetime_bound("2026-01-01T10:00:00+00:00"),
            datetime(2026, 1, 1, 10, 0, tzinfo=dt_timezone.utc),
        )
        self.assertIsNone(parse_analytics_datetime_bound("not-a-date"))
        self.assertIsNone(parse_analytics_datetime_bound(""))

    def test_single_day_filter_includes_lobbies_started_that_day(self):
        """The user-visible symptom: from=X&to=X returned nothing."""
        now = timezone.now()
        lobby = self._create_lobby(
            name="default",
            start_time=datetime(2026, 3, 4, 13, 45, tzinfo=BERLIN),
            end_time=datetime(2026, 3, 4, 15, 0, tzinfo=BERLIN),
        )
        del now
        qs = filtered_lobby_queryset(
            lobby_name="default",
            from_dt=parse_analytics_datetime_bound("2026-03-04"),
            to_dt=parse_analytics_datetime_bound("2026-03-04", end_of_day=True),
        )
        self.assertTrue(qs.filter(pk=lobby.pk).exists())

    def test_parse_analytics_datetime_bound_uses_berlin_for_date_only(self):
        berlin_midnight = parse_analytics_datetime_bound("2026-01-01")
        self.assertEqual(berlin_midnight.tzinfo, BERLIN)
        self.assertEqual(berlin_midnight.hour, 0)

        lobby = self._create_lobby(
            name="default",
            start_time=datetime(2026, 1, 1, 0, 30, tzinfo=BERLIN),
            end_time=datetime(2026, 1, 1, 2, 0, tzinfo=BERLIN),
        )
        qs = filtered_lobby_queryset(
            lobby_name="default",
            from_dt=parse_analytics_datetime_bound("2026-01-01"),
            to_dt=parse_analytics_datetime_bound("2026-01-01", end_of_day=True),
        )
        self.assertTrue(qs.filter(pk=lobby.pk).exists())

    def test_total_users_counts_distinct_users(self):
        learner = self._create_user("distinct_learner")
        volunteer = self._create_user("distinct_volunteer")
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(hours=2),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=True)
        RandomCallLobbyUser.objects.create(user=volunteer, lobby=lobby, is_active=False)

        snap = build_snapshots(annotate_lobby_metrics(RandomCallLobby.objects.filter(pk=lobby.pk)))[lobby.uuid]
        self.assertEqual(snap.total_users, 2)

    def test_apply_lobby_ordering_includes_pk_tiebreaker(self):
        """Paging over a non-unique sort column repeats and drops rows without a tiebreaker.

        `total_users` is an annotation, so the queryset has to be annotated before it can
        be ordered by it — ordering a bare queryset raised FieldError and this test never
        exercised the tiebreaker at all.
        """
        qs = apply_lobby_ordering(annotate_lobby_metrics(RandomCallLobby.objects.none()), "total_users")
        self.assertEqual(list(qs.query.order_by), ["total_users", "-pk"])

    def test_apply_lobby_ordering_rejects_unknown_column(self):
        """The allow-list exists so an arbitrary client string cannot reach order_by."""
        with self.assertRaisesRegex(ValueError, "Invalid ordering"):
            apply_lobby_ordering(RandomCallLobby.objects.none(), "not_a_column")

    def test_invalid_lobby_uuid_returns_400(self):
        from rest_framework.test import APIClient

        user = self._create_admin_user("invalid_uuid")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/random_calls/analytics/lobby/default/instance?lobby_uuid=not-a-uuid")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid lobby_uuid")

    def test_resolve_lobby_instance_rejects_malformed_uuid(self):
        with self.assertRaises(InvalidLobbyUuid):
            resolve_lobby_instance("default", lobby_uuid="abc")

    def test_is_lobby_active_handles_null_times(self):
        lobby = RandomCallLobby.objects.create(name="default")
        self.assertFalse(is_lobby_active(lobby))

    def test_detail_endpoint_handles_null_lobby_times(self):
        learner = self._create_user("null_times_learner")
        lobby = RandomCallLobby.objects.create(name="default")
        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=True)

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self._create_admin_user("null_times"))
        response = client.get(f"/api/random_calls/analytics/lobby/default/instance?lobby_uuid={lobby.uuid}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["lobby"]["is_active"])

    def test_webhook_completion_scoped_to_accepted_lobby_matching(self):
        learner = self._create_user("wh_learner")
        volunteer = self._create_user("wh_volunteer")
        old_lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(days=14),
            end_time=timezone.now() - timezone.timedelta(days=14) + timezone.timedelta(hours=2),
        )
        new_lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(hours=2),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        old_match = RandomCallMatching.objects.create(
            lobby=old_lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=False,
            accepted_at=old_lobby.start_time + timezone.timedelta(minutes=5),
        )
        new_match = RandomCallMatching.objects.create(
            lobby=new_lobby,
            u1=learner,
            u2=volunteer,
            accepted=True,
            completed=False,
            accepted_at=new_lobby.start_time + timezone.timedelta(minutes=5),
        )
        session_created_at = new_lobby.start_time + timezone.timedelta(minutes=10)
        matching = _matching_for_completed_random_call(
            learner,
            volunteer,
            session_created_at=session_created_at,
        )
        self.assertEqual(matching.pk, new_match.pk)
        RandomCallMatching.objects.filter(pk=matching.pk).update(
            completed=True,
            completed_at=timezone.now(),
        )
        old_match.refresh_from_db()
        new_match.refresh_from_db()
        self.assertFalse(old_match.completed)
        self.assertTrue(new_match.completed)

    def test_list_api_legacy_orphan_row_returns_200(self):
        learner = self._create_user("legacy_list_learner")
        volunteer = self._create_user("legacy_list_volunteer")
        lobby = self._create_lobby(
            name="default",
            start_time=timezone.now() - timezone.timedelta(days=2),
            end_time=timezone.now() - timezone.timedelta(days=2) + timezone.timedelta(hours=2),
        )
        RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            completed=True,
            accepted=False,
        )

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self._create_admin_user("legacy_list"))
        response = client.get("/api/random_calls/analytics/lobbies", {"lobby_name": "default"})
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data["results"] if item["lobby_uuid"] == str(lobby.uuid))
        self.assertEqual(row["bucket_mismatch"], 0)
        self.assertEqual(row["proposals_expired"], 1)

    def test_detail_live_lobby_inactive_user_returns_200(self):
        learner = self._create_user("live_inactive_learner")
        volunteer = self._create_user("live_inactive_volunteer")
        lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(minutes=30),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        RandomCallLobbyUser.objects.create(user=learner, lobby=lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=volunteer, lobby=lobby, is_active=True)
        RandomCallMatching.objects.create(
            lobby=lobby,
            u1=learner,
            u2=volunteer,
            created_at=timezone.now() - timezone.timedelta(minutes=5),
        )

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self._create_admin_user("live_inactive"))
        response = client.get(f"/api/random_calls/analytics/lobby/default/instance?lobby_uuid={lobby.uuid}")
        self.assertEqual(response.status_code, 200)
        snapshot = response.data["snapshot"]
        self.assertIsNotNone(snapshot)
        self.assertFalse(snapshot["proposals_are_final"])
        self.assertIn("first_time_users", snapshot)
        stats = response.data["proposal_statistics"]
        for key in ("pending", "accepted", "rejected", "expired", "dangling"):
            self.assertEqual(
                stats[f"{key}_count"],
                len(response.data["match_proposals"][key]),
                key,
            )

    def test_detail_live_lobby_exposes_attendance_snapshot(self):
        returning_user = self._create_user("live_returning")
        first_time_user = self._create_user("live_first_time")
        earlier_lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(days=14),
            end_time=timezone.now() - timezone.timedelta(days=14, hours=-2),
        )
        live_lobby = self._create_lobby(
            start_time=timezone.now() - timezone.timedelta(minutes=30),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )
        RandomCallLobbyUser.objects.create(user=returning_user, lobby=earlier_lobby, is_active=False)
        RandomCallLobbyUser.objects.create(user=returning_user, lobby=live_lobby, is_active=True)
        RandomCallLobbyUser.objects.create(user=first_time_user, lobby=live_lobby, is_active=True)

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self._create_admin_user("live_attendance"))
        response = client.get(f"/api/random_calls/analytics/lobby/default/instance?lobby_uuid={live_lobby.uuid}")
        self.assertEqual(response.status_code, 200)
        snapshot = response.data["snapshot"]
        self.assertIsNotNone(snapshot)
        self.assertFalse(snapshot["proposals_are_final"])
        self.assertEqual(snapshot["first_time_users"], 1)
        self.assertEqual(snapshot["returning_users"], 1)
        self.assertEqual(snapshot["completed_calls"], 0)
