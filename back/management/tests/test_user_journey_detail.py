"""Admin user-detail extras: V5 journey stepper stages."""

from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from management.analytics.user_journey.catalog import CATALOG
from management.analytics.user_journey.detail import user_journey_stages
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.profile import Profile
from management.models.state import State
from management.models.unconfirmed_matches import ProposedMatch
from management.models.user import User


def _user(label: str, *, state=None, user_type=None) -> User:
    user = User.objects.create_user(
        email=f"{label}-{uuid4()}@example.com",
        password="Test123!",
        first_name=label.title(),
        last_name="User",
    )
    if state:
        State.objects.filter(user=user).update(**state)
    if user_type is not None:
        Profile.objects.filter(user=user).update(user_type=user_type)
    user.refresh_from_db()
    return user


def _onboarded(label: str, *, searching=True, **state) -> User:
    return _user(
        label,
        user_type=Profile.TypeChoices.VOLUNTEER,
        state={
            "user_form_state": State.UserFormStateChoices.FILLED,
            "email_authenticated": True,
            "is_onboarded": True,
            "searching_state": (
                State.SearchingStateChoices.SEARCHING if searching else State.SearchingStateChoices.IDLE
            ),
            **state,
        },
    )


def _ids(stages: dict) -> list[str]:
    return [stage["id"] for stage in stages["stages"]]


def _by_id(stages: dict, stage_id: str) -> dict:
    return next(stage for stage in stages["stages"] if stage["id"] == stage_id)


class UserJourneyDetailTests(TestCase):
    def test_new_user_is_on_registered(self):
        user = _user("created")
        stages = user_journey_stages(user, bucket="state__email_unverified")

        self.assertEqual(
            _ids(stages),
            ["registered", "email_verified", "form_completed", "onboarding", "onboarded", "matching", "success"],
        )
        self.assertTrue(_by_id(stages, "registered")["achieved"])
        self.assertFalse(_by_id(stages, "email_verified")["achieved"])
        self.assertEqual(stages["active_stage_index"], 0)
        self.assertEqual(_by_id(stages, "email_verified")["label"], CATALOG["funnel__email_verified"].display_name)

    def test_form_complete_waits_at_onboarding_not_started(self):
        user = _user(
            "form_done",
            user_type=Profile.TypeChoices.VOLUNTEER,
            state={
                "user_form_state": State.UserFormStateChoices.FILLED,
                "email_authenticated": True,
                "user_form_completed_at": timezone.now() - timedelta(days=2),
            },
        )
        stages = user_journey_stages(user, bucket="state__onboarding_not_started")

        self.assertTrue(_by_id(stages, "form_completed")["achieved"])
        self.assertFalse(_by_id(stages, "onboarding")["achieved"])
        self.assertEqual(_by_id(stages, "onboarding")["label"], CATALOG["funnel__onboarding_started"].display_name)
        self.assertEqual(stages["active_stage_index"], 2)

    def test_booked_onboarding_uses_the_v5_bucket_label(self):
        user = _user(
            "booked",
            user_type=Profile.TypeChoices.VOLUNTEER,
            state={
                "user_form_state": State.UserFormStateChoices.FILLED,
                "email_authenticated": True,
            },
        )
        start = timezone.now() + timedelta(days=3)
        PreMatchingAppointment.objects.create(user=user, start_time=start, end_time=start)
        stages = user_journey_stages(user, bucket="state__onboarding_booked")

        onboarding = _by_id(stages, "onboarding")
        self.assertTrue(onboarding["achieved"])
        self.assertEqual(onboarding["label"], CATALOG["state__onboarding_booked"].display_name)
        self.assertFalse(_by_id(stages, "onboarded")["achieved"])
        self.assertEqual(stages["active_stage_index"], 3)

    def test_ineligible_onboarding_is_the_active_branch(self):
        user = _user(
            "ineligible",
            user_type=Profile.TypeChoices.LEARNER,
            state={
                "user_form_state": State.UserFormStateChoices.FILLED,
                "email_authenticated": True,
            },
        )
        stages = user_journey_stages(user, bucket="state__onboarding_ineligible")

        self.assertEqual(_by_id(stages, "onboarding")["label"], CATALOG["state__onboarding_ineligible"].display_name)
        self.assertTrue(_by_id(stages, "onboarding")["achieved"])
        self.assertFalse(_by_id(stages, "onboarded")["achieved"])
        self.assertEqual(stages["active_stage_index"], 3)

    def test_searching_for_first_match_uses_the_v5_cell(self):
        user = _onboarded("searching")
        stages = user_journey_stages(user, bucket="state__first_search_no_proposal")

        matching = _by_id(stages, "matching")
        self.assertTrue(_by_id(stages, "onboarded")["achieved"])
        self.assertTrue(matching["achieved"])
        self.assertEqual(matching["label"], CATALOG["state__first_search_no_proposal"].display_name)
        self.assertFalse(_by_id(stages, "success")["achieved"])
        self.assertEqual(stages["active_stage_index"], 5)

    def test_open_proposal_is_the_matching_step(self):
        user = _onboarded("proposed")
        partner = _onboarded("proposal_partner")
        ProposedMatch.objects.create(
            user1=user,
            user2=partner,
            closed=False,
            expires_at=timezone.now() + timedelta(days=3),
        )
        stages = user_journey_stages(user, bucket="state__proposed")

        self.assertEqual(_by_id(stages, "matching")["label"], CATALOG["state__proposed"].display_name)
        self.assertEqual(stages["active_stage_index"], 5)

    def test_first_match_kickoff_is_the_matching_step(self):
        user = _onboarded("kickoff")
        partner = _onboarded("kickoff_partner", searching=False)
        Match.objects.create(user1=user, user2=partner, support_matching=False, active=True, confirmed=False)
        stages = user_journey_stages(user, bucket="state__first_match_kickoff")

        matching = _by_id(stages, "matching")
        self.assertEqual(matching["label"], CATALOG["state__first_match_kickoff"].display_name)
        self.assertTrue(matching["achieved"])
        self.assertIsNotNone(matching["achieved_at"])
        self.assertFalse(_by_id(stages, "success")["achieved"])

    def test_success_uses_the_v5_two_by_two_cell(self):
        user = _onboarded("success", searching=False)
        partner = _onboarded("success_partner", searching=False)
        Match.objects.create(
            user1=user,
            user2=partner,
            support_matching=False,
            active=True,
            confirmed=True,
            completed_off_plattform=True,
        )
        stages = user_journey_stages(user, bucket="state__success_ongoing_settled")

        self.assertEqual(_by_id(stages, "matching")["label"], "In a match")
        outcome = _by_id(stages, "success")
        self.assertTrue(outcome["achieved"])
        self.assertEqual(outcome["label"], CATALOG["state__success_ongoing_settled"].display_name)
        self.assertEqual(stages["active_stage_index"], 6)

    def test_unresponsive_after_success_is_the_terminal_step(self):
        user = _onboarded("gone", searching=False, unresponsive=True)
        partner = _onboarded("gone_partner", searching=False)
        Match.objects.create(
            user1=user,
            user2=partner,
            support_matching=False,
            completed_off_plattform=True,
        )
        stages = user_journey_stages(user, bucket="state__unresponsive_after_success")

        self.assertEqual(_by_id(stages, "matching")["label"], "In a match")
        terminal = _by_id(stages, "unresponsive_after_success")
        self.assertTrue(terminal["achieved"])
        self.assertEqual(terminal["label"], CATALOG["state__unresponsive_after_success"].display_name)
        self.assertEqual(stages["active_stage_index"], 6)
