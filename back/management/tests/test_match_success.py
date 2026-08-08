"""Match token / success versions: banding, accrual, registry, and session eligibility."""

import dataclasses
from datetime import timedelta
from uuid import uuid4

from django.test import SimpleTestCase, TestCase
from video.models import LivekitSession

from management.match_success import (
    ACTIVE_VERSION_ID,
    activatable_version_ids,
    annotate_match_tokens,
    get_version,
    list_versions,
    match_is_successful,
    match_tokens,
    match_tokens_by_id,
    match_total_minutes,
    success_token_threshold,
    successful_match_ids,
    tokens_from_total_minutes,
)
from management.match_success.sessions import qualifying_sessions
from management.match_success.versions import _assert_active_version_is_activatable
from management.match_success.versions.base import MatchOutcomeVersion
from management.match_success.versions.v1_total_minutes import (
    MINUTE_TOKEN_THRESHOLDS,
    MINUTES_PER_TOKEN_AFTER_SUCCESS,
    SUCCESS_MINUTES,
    SUCCESS_TOKEN_THRESHOLD,
)
from management.models.matches import Match
from management.models.user import User


def _user(label: str) -> User:
    return User.objects.create_user(
        email=f"{label}-{uuid4()}@example.com",
        password="Test123!",
        first_name="Test",
        last_name=label,
    )


class V1TotalMinutesBandingTests(SimpleTestCase):
    def test_band_edges(self):
        cases = (
            (0, 0),
            (24.9, 0),
            (25, 1),
            (54.9, 1),
            (55, 2),
            (79.9, 2),
            (80, 3),
            (104.9, 3),
            (105, 4),
            (129.9, 4),
            (130, 5),
            (154.9, 5),
            (155, 6),
            (179.9, 6),
            (180, 7),
            (204.9, 7),
            (205, 8),
        )
        for minutes, expected in cases:
            with self.subTest(minutes=minutes):
                self.assertEqual(tokens_from_total_minutes(minutes), expected)

    def test_tokens_keep_accruing_past_success(self):
        """Success is the threshold, not the top of the scale."""
        cases = (
            (205, 8),
            (234.9, 8),
            (235, 9),
            (264.9, 9),
            (265, 10),
            (3880, 8 + ((3880 - 205) // 30)),
        )
        for minutes, expected in cases:
            with self.subTest(minutes=minutes):
                self.assertEqual(tokens_from_total_minutes(minutes), expected)

    def test_accrual_is_continuous_at_the_success_boundary(self):
        just_under = tokens_from_total_minutes(SUCCESS_MINUTES - 0.1)
        at = tokens_from_total_minutes(SUCCESS_MINUTES)
        self.assertEqual(just_under, SUCCESS_TOKEN_THRESHOLD - 1)
        self.assertEqual(at, SUCCESS_TOKEN_THRESHOLD)

    def test_tokens_never_decrease_as_minutes_grow(self):
        previous = 0
        for minutes in range(0, 1200, 5):
            current = tokens_from_total_minutes(minutes)
            self.assertGreaterEqual(current, previous, f"went backwards at {minutes} minutes")
            previous = current

    def test_success_token_threshold_is_eight(self):
        self.assertEqual(success_token_threshold("v1"), 8)
        self.assertEqual(tokens_from_total_minutes(SUCCESS_MINUTES), success_token_threshold("v1"))

    def test_thresholds_are_ordered_ascending(self):
        """The banding loop stops at the first unmet band, so order is load-bearing."""
        minutes = [m for m, _ in MINUTE_TOKEN_THRESHOLDS]
        tokens = [t for _, t in MINUTE_TOKEN_THRESHOLDS]
        self.assertEqual(minutes, sorted(minutes))
        self.assertEqual(tokens, sorted(tokens))


class VersionRegistryTests(SimpleTestCase):
    def test_active_version_is_v1(self):
        self.assertEqual(ACTIVE_VERSION_ID, "v1")
        self.assertEqual(get_version().id, "v1")
        self.assertTrue(get_version().uses_tokens)

    def test_v0_is_legacy_completed_match_not_tokens(self):
        v0 = get_version("v0")
        self.assertFalse(v0.uses_tokens)
        self.assertIsNone(v0.success_token_threshold)
        with self.assertRaisesRegex(ValueError, "not a token system"):
            match_tokens(object(), version="v0")
        with self.assertRaisesRegex(ValueError, "no token target"):
            success_token_threshold("v0")

    def test_v0_is_comparison_only(self):
        self.assertFalse(get_version("v0").can_be_active)
        self.assertEqual(activatable_version_ids(), ("v1",))

    def test_both_versions_are_registered(self):
        self.assertEqual({v.id for v in list_versions()}, {"v0", "v1"})

    def test_unknown_version_raises(self):
        with self.assertRaisesRegex(ValueError, "Unknown match-success version"):
            get_version("v99")

    def test_activating_a_comparison_only_version_is_rejected(self):
        """Guards the boot landmine: selecting v0 must fail loudly, at import, saying why."""
        from management.match_success import versions

        original = versions.ACTIVE_VERSION_ID
        try:
            versions.ACTIVE_VERSION_ID = "v0"
            with self.assertRaisesRegex(ValueError, "comparison-only"):
                _assert_active_version_is_activatable()
        finally:
            versions.ACTIVE_VERSION_ID = original

    def test_activating_an_unregistered_version_is_rejected(self):
        from management.match_success import versions

        original = versions.ACTIVE_VERSION_ID
        try:
            versions.ACTIVE_VERSION_ID = "v99"
            with self.assertRaisesRegex(ValueError, "not registered"):
                _assert_active_version_is_activatable()
        finally:
            versions.ACTIVE_VERSION_ID = original

    def test_an_activatable_version_must_define_tokens(self):
        """A version production can select has to be able to answer match_tokens."""
        with self.assertRaisesRegex(ValueError, "must define both"):
            MatchOutcomeVersion(
                id="broken",
                title="Broken",
                description="",
                successful_matches_fn=lambda qs: qs.none(),
            )

    def test_every_activatable_version_has_a_token_scale(self):
        for version in list_versions():
            if version.can_be_active:
                self.assertTrue(version.uses_tokens, f"{version.id} is activatable without tokens")
                self.assertIsNotNone(version.success_token_threshold)

    def test_every_version_answers_in_bulk(self):
        """Comparing two versions across the match table must not be one query per match."""
        for version in list_versions():
            self.assertIsNotNone(version.successful_matches_fn, f"{version.id} has no batch predicate")

    def test_success_has_exactly_one_implementation_per_version(self):
        """No row-form override exists, so `is_successful` cannot disagree with the batch form.

        v1 briefly carried both, written independently — the row form checked
        `completed_off_plattform or tokens >= threshold` while the queryset form filtered
        on minutes. Editing one and forgetting the other is the drift this package exists
        to prevent, so the field is gone and the base derives the row answer.
        """
        fields = {f.name for f in dataclasses.fields(MatchOutcomeVersion)}
        self.assertIn("successful_matches_fn", fields)
        self.assertNotIn("is_successful_fn", fields)


class QualifyingSessionTests(TestCase):
    """Which calls count. This is where the judgement lives, and it was untested."""

    @classmethod
    def setUpTestData(cls):
        cls.a = _user("a")
        cls.b = _user("b")
        cls.outsider = _user("outsider")
        cls.match = Match.objects.create(user1=cls.a, user2=cls.b)
        cls.match_start = cls.match.created_at

    def _session(self, u1, u2, *, minutes=60, starts_after=timedelta(hours=1), both_active=True, finished=True):
        started = self.match_start + starts_after
        session = LivekitSession.objects.create(u1=u1, u2=u2, both_have_been_active=both_active)
        LivekitSession.objects.filter(pk=session.pk).update(
            created_at=started,
            end_time=started + timedelta(minutes=minutes) if finished else None,
        )
        session.refresh_from_db()
        return session

    def test_a_finished_mutual_call_counts(self):
        self._session(self.a, self.b, minutes=90)
        self.assertEqual(qualifying_sessions(self.match).count(), 1)
        self.assertAlmostEqual(match_total_minutes(self.match), 90, places=1)

    def test_the_pair_counts_in_either_direction(self):
        self._session(self.a, self.b, minutes=30)
        self._session(self.b, self.a, minutes=30, starts_after=timedelta(hours=2))
        self.assertEqual(qualifying_sessions(self.match).count(), 2)
        self.assertAlmostEqual(match_total_minutes(self.match), 60, places=1)

    def test_a_call_with_someone_else_does_not_count(self):
        self._session(self.a, self.outsider, minutes=300)
        self.assertEqual(qualifying_sessions(self.match).count(), 0)
        self.assertEqual(match_total_minutes(self.match), 0)

    def test_a_call_before_the_match_started_does_not_count(self):
        self._session(self.a, self.b, minutes=300, starts_after=timedelta(days=-1))
        self.assertEqual(qualifying_sessions(self.match).count(), 0)

    def test_a_call_where_only_one_side_was_active_does_not_count(self):
        self._session(self.a, self.b, minutes=300, both_active=False)
        self.assertEqual(qualifying_sessions(self.match).count(), 0)

    def test_an_unfinished_call_does_not_count(self):
        self._session(self.a, self.b, finished=False)
        self.assertEqual(qualifying_sessions(self.match).count(), 0)

    def test_minutes_accumulate_across_calls_into_tokens(self):
        for index in range(4):
            self._session(self.a, self.b, minutes=60, starts_after=timedelta(days=index + 1))
        self.assertAlmostEqual(match_total_minutes(self.match), 240, places=1)
        # 240 min = 8 tokens at 205, plus one more for the 30 minutes past it.
        self.assertEqual(match_tokens(self.match), 9)


class BatchTokenTests(TestCase):
    """The batch form is the primitive; the single-row form must agree with it."""

    @classmethod
    def setUpTestData(cls):
        cls.matches = []
        for minutes in (0, 30, 210, 400):
            u1 = _user("u1")
            u2 = _user("u2")
            match = Match.objects.create(user1=u1, user2=u2)
            if minutes:
                started = match.created_at + timedelta(hours=1)
                session = LivekitSession.objects.create(u1=u1, u2=u2, both_have_been_active=True)
                LivekitSession.objects.filter(pk=session.pk).update(
                    created_at=started, end_time=started + timedelta(minutes=minutes)
                )
            cls.matches.append((match, minutes))

    def test_batch_matches_the_per_match_result(self):
        qs = Match.objects.filter(pk__in=[m.pk for m, _ in self.matches])
        batch = match_tokens_by_id(qs)
        for match, _ in self.matches:
            self.assertEqual(batch[match.pk], match_tokens(match))

    def test_batch_expected_values(self):
        qs = Match.objects.filter(pk__in=[m.pk for m, _ in self.matches])
        batch = match_tokens_by_id(qs)
        expected = {0: 0, 30: 1, 210: 8, 400: 8 + int((400 - SUCCESS_MINUTES) // MINUTES_PER_TOKEN_AFTER_SUCCESS)}
        for match, minutes in self.matches:
            self.assertEqual(batch[match.pk], expected[minutes], f"{minutes} minutes")

    def test_annotated_queryset_makes_per_row_lookups_free(self):
        qs = annotate_match_tokens(Match.objects.filter(pk__in=[m.pk for m, _ in self.matches]))
        rows = list(qs)
        with self.assertNumQueries(0):
            for match in rows:
                match_tokens(match)

    def test_row_and_batch_success_always_agree(self):
        """The derivation is the point — assert it on data, not just on the dataclass."""
        qs = Match.objects.filter(pk__in=[m.pk for m, _ in self.matches])
        batch = successful_match_ids(qs)
        for match, _ in self.matches:
            self.assertEqual(match_is_successful(match), match.pk in batch, f"match {match.pk}")

    def test_successful_ids_agrees_with_the_threshold(self):
        qs = Match.objects.filter(pk__in=[m.pk for m, _ in self.matches])
        successful = successful_match_ids(qs)
        for match, minutes in self.matches:
            self.assertEqual(match.pk in successful, minutes >= SUCCESS_MINUTES, f"{minutes} minutes")

    def test_batch_token_lookup_is_one_query(self):
        qs = Match.objects.filter(pk__in=[m.pk for m, _ in self.matches])
        with self.assertNumQueries(1):
            match_tokens_by_id(qs)
