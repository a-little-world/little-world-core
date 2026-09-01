from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from management.api.match_proposal_stats import match_proposal_statistics
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.profile import Profile
from management.models.unconfirmed_matches import MatchType, ProposedMatch
from management.models.user import User


class MatchProposalStatisticsTests(TestCase):
    def _create_user(self, email_prefix: str, user_type: str, *, onboarded_days_ago: int) -> User:
        user = User.objects.create_user(
            email=f"{email_prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )
        user.profile.user_type = user_type
        user.profile.save(update_fields=["user_type"])
        user.state.is_onboarded = True
        user.state.self_onboarding_completed_at = (timezone.now() - timedelta(days=onboarded_days_ago)).date()
        user.state.save(update_fields=["is_onboarded", "self_onboarding_completed_at"])
        return user

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = match_proposal_statistics

        self.staff_user = self._create_user("staff", Profile.TypeChoices.VOLUNTEER, onboarded_days_ago=30)
        self.staff_user.is_staff = True
        self.staff_user.save(update_fields=["is_staff"])

    def test_waiting_time_includes_onboarded_cohort_and_still_waiting_learners(self):
        now = timezone.now()
        learner_with_proposal = self._create_user(
            "learner-with-proposal", Profile.TypeChoices.LEARNER, onboarded_days_ago=20
        )
        self._create_user("learner-still-waiting", Profile.TypeChoices.LEARNER, onboarded_days_ago=10)
        volunteer_with_match = self._create_user(
            "volunteer-with-match", Profile.TypeChoices.VOLUNTEER, onboarded_days_ago=15
        )
        self._create_user("volunteer-still-waiting", Profile.TypeChoices.VOLUNTEER, onboarded_days_ago=8)

        proposal_created_at = now - timedelta(days=5)
        proposal = ProposedMatch.objects.create(
            user1=volunteer_with_match,
            user2=learner_with_proposal,
            confirming_user=learner_with_proposal,
            match_type=MatchType.STANDARD,
            closed=True,
            rejected=False,
            expired=False,
        )
        ProposedMatch.objects.filter(pk=proposal.pk).update(potential_matching_created_at=proposal_created_at)

        match_created_at = now - timedelta(days=2)
        match = Match.objects.create(
            user1=volunteer_with_match,
            user2=learner_with_proposal,
            match_type=MatchType.STANDARD,
        )
        Match.objects.filter(pk=match.pk).update(created_at=match_created_at)

        request = self.factory.post(
            "/api/matching/match-proposals/statistics/",
            {
                "start_date": (now - timedelta(days=25)).date().isoformat(),
                "end_date": now.date().isoformat(),
                "match_type": "all",
            },
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = self.view(request)

        assert response.status_code == 200
        waiting_time = response.data["waiting_time"]

        first_proposal = waiting_time["first_proposal_learners"]
        assert first_proposal["count"] == 2
        assert first_proposal["count"] == waiting_time["first_match_learners"]["count"]
        assert first_proposal["completed_count"] == 1
        assert first_proposal["still_waiting_count"] == 1
        assert first_proposal["average_days"] == 12.5
        assert first_proposal["median_days"] == 12.5

        first_match_total = waiting_time["first_match_total"]
        assert first_match_total["count"] == 4
        assert first_match_total["completed_count"] == 2
        assert first_match_total["still_waiting_count"] == 2
        assert first_match_total["average_days"] == 12.2
        assert first_match_total["median_days"] == 11.5
        assert waiting_time["first_match_learners"]["count"] == 2
        assert waiting_time["first_match_volunteers"]["count"] == 2

    def test_volunteer_waiting_time_uses_onboarding_not_later_prematch(self):
        now = timezone.now()
        volunteer = self._create_user("volunteer-prematch", Profile.TypeChoices.VOLUNTEER, onboarded_days_ago=100)
        volunteer.state.self_onboarding_completed_at = None
        volunteer.state.onboarding_call_completed_at = now - timedelta(days=100)
        volunteer.state.had_prematching_call = True
        volunteer.state.save(
            update_fields=[
                "self_onboarding_completed_at",
                "onboarding_call_completed_at",
                "had_prematching_call",
            ]
        )

        match_created_at = now - timedelta(days=50)
        learner = self._create_user("learner-match", Profile.TypeChoices.LEARNER, onboarded_days_ago=60)
        match = Match.objects.create(
            user1=volunteer,
            user2=learner,
            match_type=MatchType.STANDARD,
        )
        Match.objects.filter(pk=match.pk).update(created_at=match_created_at)

        # Follow-up prematch long after first match — must not shrink waiting time to ~0.
        PreMatchingAppointment.objects.create(
            user=volunteer,
            start_time=now - timedelta(days=5),
            end_time=now - timedelta(days=5, hours=-1),
        )

        request = self.factory.post(
            "/api/matching/match-proposals/statistics/",
            {
                "start_date": (now - timedelta(days=105)).date().isoformat(),
                "end_date": (now - timedelta(days=95)).date().isoformat(),
                "match_type": "all",
            },
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = self.view(request)

        assert response.status_code == 200
        volunteer_stats = response.data["waiting_time"]["first_match_volunteers"]
        assert volunteer_stats["completed_count"] == 1
        assert volunteer_stats["average_days"] == 50.0
        assert volunteer_stats["median_days"] == 50.0

    def test_first_proposal_outcome_waiting_time_uses_only_first_proposals(self):
        now = timezone.now()
        learner = self._create_user("learner-outcomes", Profile.TypeChoices.LEARNER, onboarded_days_ago=40)
        volunteer = self._create_user("volunteer-outcomes", Profile.TypeChoices.VOLUNTEER, onboarded_days_ago=40)

        first_proposal = ProposedMatch.objects.create(
            user1=volunteer,
            user2=learner,
            confirming_user=learner,
            match_type=MatchType.STANDARD,
            closed=True,
            expired=True,
        )
        ProposedMatch.objects.filter(pk=first_proposal.pk).update(
            potential_matching_created_at=now - timedelta(days=30)
        )

        second_proposal = ProposedMatch.objects.create(
            user1=volunteer,
            user2=learner,
            confirming_user=learner,
            match_type=MatchType.STANDARD,
            closed=True,
            rejected=False,
            expired=False,
        )
        ProposedMatch.objects.filter(pk=second_proposal.pk).update(
            potential_matching_created_at=now - timedelta(days=5)
        )

        request = self.factory.post(
            "/api/matching/match-proposals/statistics/",
            {
                "start_date": (now - timedelta(days=35)).date().isoformat(),
                "end_date": now.date().isoformat(),
                "match_type": "all",
            },
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = self.view(request)

        assert response.status_code == 200
        outcome_waiting = response.data["first_proposal_outcome_waiting_time"]
        assert outcome_waiting["total_first_proposals"] == 1
        assert outcome_waiting["expired"]["count"] == 1
        assert outcome_waiting["expired"]["average_days"] == 10.0
        assert outcome_waiting["accepted"]["count"] == 0
