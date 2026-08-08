from uuid import uuid4

from django.test import TestCase

from management.analytics.registry import get_catalog_entry
from management.api.match_journey_filter_list import (
    determine_match_bucket,
    get_match_bucket_label,
)
from management.models.matches import Match
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
