from uuid import uuid4

from django.test import TestCase

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

    def test_random_call_match_uses_organic_match_bucket(self):
        user1 = self._create_user("organic-user1")
        user2 = self._create_user("organic-user2")
        match = Match.objects.create(
            user1=user1,
            user2=user2,
            match_type=MatchType.RANDOM_CALL,
        )

        assert determine_match_bucket(match.pk) == "match_journey_v2__organic_match"
        assert get_match_bucket_label(determine_match_bucket(match.pk)) == "Organic Match"

    def test_standard_match_does_not_use_organic_match_bucket(self):
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

        assert determine_match_bucket(match.pk) != "match_journey_v2__organic_match"
