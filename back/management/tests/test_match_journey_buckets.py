from uuid import uuid4

from django.test import TestCase

from management.analytics.registry import get_catalog_entry
from management.api.match_journey_filter_list import (
    determine_match_bucket,
    determine_match_buckets,
    get_match_bucket_label,
)
from management.api.match_journey_filters import all_matches, match_unviewed
from management.api.user_journey_filters import first_search_v2
from management.models.matches import Match
from management.models.profile import Profile
from management.models.state import State
from management.models.unconfirmed_matches import MatchType
from management.models.user import User


class MatchJourneyBucketTests(TestCase):
    def _create_user(self, email_prefix: str) -> User:
        return User.objects.create_user(
            email=f"{email_prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )

    def test_standard_unconfirmed_match_uses_v5_unviewed_bucket(self):
        user1 = self._create_user("standard-user1")
        user2 = self._create_user("standard-user2")
        match = Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.STANDARD,
            active=True,
            support_matching=False,
            confirmed=False,
        )

        assert determine_match_bucket(match.pk) == "match_state__unviewed"
        assert (
            get_match_bucket_label(determine_match_bucket(match.pk))
            == get_catalog_entry("match_state__unviewed").display_name
        )

    def test_support_match_uses_support_bucket(self):
        user1 = self._create_user("support-user1")
        user2 = self._create_user("support-user2")
        match = Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.STANDARD,
            active=True,
            support_matching=True,
            confirmed=False,
        )

        assert determine_match_bucket(match.pk) == "special__support_matching"
        assert get_match_bucket_label(determine_match_bucket(match.pk)) == "Support matching"

    def test_random_call_match_uses_v5_bucket_not_legacy_organic(self):
        user1 = self._create_user("organic-user1")
        user2 = self._create_user("organic-user2")
        match = Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.RANDOM_CALL,
            active=True,
            support_matching=False,
            confirmed=False,
        )

        bucket = determine_match_bucket(match.pk)
        assert bucket == "match_state__unviewed"
        assert bucket != "match_journey_v2__organic_match"

    def test_random_call_match_is_in_v2_unviewed_list(self):
        user1 = self._create_user("rc-v2-user1")
        user2 = self._create_user("rc-v2-user2")
        match = Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.RANDOM_CALL,
            active=True,
            support_matching=False,
            confirmed=False,
        )

        assert match_unviewed(Match.objects.filter(pk=match.pk)).exists()
        assert "match_journey_v2__unviewed" in determine_match_buckets(match.pk, all_lists=True)

    def test_temporary_match_is_excluded_from_v2_and_v5_baselines(self):
        user1 = self._create_user("tmp-user1")
        user2 = self._create_user("tmp-user2")
        match = Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.TEMPORARY,
            active=False,
            support_matching=False,
            confirmed=True,
        )

        assert not all_matches(Match.objects.filter(pk=match.pk)).exists()
        assert determine_match_bucket(match.pk) is None

    def test_unconfirmed_random_call_with_lobby_video_is_in_flight(self):
        user1 = self._create_user("rc-video-user1")
        user2 = self._create_user("rc-video-user2")
        match = Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.RANDOM_CALL,
            active=True,
            support_matching=False,
            confirmed=False,
            total_mutal_video_calls_counter=1,
        )

        assert determine_match_bucket(match.pk) == "match_state__tokens_0"


class FirstSearchRandomCallMatchTests(TestCase):
    def _searching_volunteer(self, email_prefix: str) -> User:
        user = User.objects.create_user(
            email=f"{email_prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )
        Profile.objects.filter(user=user).update(user_type=Profile.TypeChoices.VOLUNTEER)
        State.objects.filter(user=user).update(
            user_form_state=State.UserFormStateChoices.FILLED,
            searching_state=State.SearchingStateChoices.SEARCHING,
            email_authenticated=True,
            unresponsive=False,
            is_onboarded=True,
        )
        return user

    def test_random_call_match_leaves_first_search(self):
        user1 = self._searching_volunteer("fs-rc-1")
        user2 = self._searching_volunteer("fs-rc-2")
        Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.RANDOM_CALL,
            support_matching=False,
            active=True,
            confirmed=False,
        )

        assert not first_search_v2(User.objects.filter(pk=user1.pk), require_min_lang_level=False).exists()
        assert not first_search_v2(User.objects.filter(pk=user2.pk), require_min_lang_level=False).exists()

    def test_temporary_lobby_match_stays_in_first_search(self):
        user1 = self._searching_volunteer("fs-tmp-1")
        user2 = self._searching_volunteer("fs-tmp-2")
        Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.TEMPORARY,
            support_matching=False,
            active=False,
            confirmed=True,
        )

        assert first_search_v2(User.objects.filter(pk=user1.pk), require_min_lang_level=False).exists()
        assert first_search_v2(User.objects.filter(pk=user2.pk), require_min_lang_level=False).exists()
