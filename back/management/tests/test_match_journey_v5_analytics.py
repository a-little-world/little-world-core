"""Match Journey V5 — structural validation (no DB required for these checks)."""

import inspect
from uuid import uuid4

from django.test import SimpleTestCase, TestCase

from management.analytics.core.roles import CatalogRole
from management.analytics.match_journey.catalog import CATALOG, DOMAIN_PREFIXES
from management.analytics.match_journey.cohorts import MatchPartitionCohort
from management.analytics.match_journey.partitions import MATCH_JOURNEY_V5
from management.analytics.match_journey.queries import state
from management.analytics.match_journey.queries.state import ENGAGEMENT_DAYS, FAILURE_CLIFF_DAYS
from management.analytics.registry import (
    ALL_PARTITIONS,
    assert_composites_valid_strict,
    assert_partition_valid_strict,
    get_partition,
    partition_buckets_with_disallowed_roles,
)
from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType
from management.models.user import User


class MatchJourneyV5StructureTests(SimpleTestCase):
    def test_v5_is_registered(self):
        self.assertIn(MATCH_JOURNEY_V5, ALL_PARTITIONS)
        self.assertIs(get_partition("match-journey-v5"), MATCH_JOURNEY_V5)

    def test_v5_passes_structural_validation(self):
        assert_partition_valid_strict(MATCH_JOURNEY_V5)
        assert_composites_valid_strict()

    def test_entity_is_match(self):
        self.assertIs(MATCH_JOURNEY_V5.base_model, Match)
        for list_id in MATCH_JOURNEY_V5.all_list_ids():
            self.assertIs(CATALOG[list_id].base_model, Match)

    def test_prefixes_are_entity_qualified(self):
        self.assertEqual(DOMAIN_PREFIXES, ("match_funnel__", "match_state__"))
        for key in CATALOG:
            self.assertTrue(key.startswith(DOMAIN_PREFIXES), key)

    def test_phase_order(self):
        self.assertEqual(
            [phase.id for phase in MATCH_JOURNEY_V5.phases],
            ["kickoff", "in_flight", "successful", "failed", "inactive", "other"],
        )

    def test_inactive_splits_closing_kind_by_stage(self):
        inactive = next(phase for phase in MATCH_JOURNEY_V5.phases if phase.id == "inactive")
        self.assertEqual(
            [b.list_id for b in inactive.buckets],
            [
                f"match_state__{kind}_{stage}"
                for kind in ("reported", "unmatched", "account_deleted", "ghosted", "unrecorded")
                for stage in ("before_success", "kickoff")
            ],
        )
        failed = next(phase for phase in MATCH_JOURNEY_V5.phases if phase.id == "failed")
        self.assertNotIn("match_state__failed_reported", [b.list_id for b in failed.buckets])

    def test_inactive_excludes_the_successful_stage(self):
        """Matches that already succeeded before closing are grouped under Successful."""
        inactive = next(phase for phase in MATCH_JOURNEY_V5.phases if phase.id == "inactive")
        for kind in ("reported", "unmatched", "account_deleted", "ghosted", "unrecorded"):
            self.assertNotIn(f"match_state__{kind}_successful", [b.list_id for b in inactive.buckets])

    def test_every_closing_kind_is_a_real_outcome_or_named_as_missing(self):
        """ "Removed" used to absorb ghosting, account deletion and *no record at all*."""
        self.assertEqual(
            state.CLOSING_KINDS,
            ("reported", "unmatched", "account_deleted", "ghosted", "unrecorded"),
        )
        # The raw values the model actually writes must each map somewhere explicit.
        self.assertEqual(
            set(state._KIND_BY_RAW),
            {"report", "unmatch", "user_deleted", "ghosted"},
        )

    def test_unknown_or_missing_closing_kind_is_unrecorded(self):
        """A match with no closing entry must not be reported as deliberately removed."""

        class FakeMatch:
            def __init__(self, report_unmatch):
                self.report_unmatch = report_unmatch

        self.assertEqual(state._closing_kind(FakeMatch([])), "unrecorded")
        self.assertEqual(state._closing_kind(FakeMatch(None)), "unrecorded")
        self.assertEqual(state._closing_kind(FakeMatch(["not-a-dict"])), "unrecorded")
        self.assertEqual(state._closing_kind(FakeMatch([{"kind": "who_knows"}])), "unrecorded")
        self.assertEqual(state._closing_kind(FakeMatch([{"kind": "unmatch"}])), "unmatched")
        self.assertEqual(state._closing_kind(FakeMatch([{"kind": "user_deleted"}])), "account_deleted")
        self.assertEqual(state._closing_kind(FakeMatch([{"kind": "report"}])), "reported")

    def test_last_entry_decides_the_closing_kind(self):
        class FakeMatch:
            def __init__(self):
                self.report_unmatch = [{"kind": "ghosted"}, {"kind": "report"}]

        self.assertEqual(state._closing_kind(FakeMatch()), "reported")

    def test_token_cache_is_scoped_to_a_run_not_a_thread(self):
        """A thread-local cache is never invalidated, so a worker serves stale counts."""
        root = Match.objects.none()
        self.assertIsNone(state._RUN_CACHE.get())
        with state.classification_run(root_qs=root):
            self.assertEqual(state._RUN_CACHE.get(), {"root_qs": root})
            with state.classification_run(root_qs=Match.objects.all()):  # re-entrant
                # Joins the outer run, so the outer scope stands — a nested call must not
                # be able to re-point the shared token map at a different queryset.
                self.assertEqual(state._RUN_CACHE.get(), {"root_qs": root})
        self.assertIsNone(state._RUN_CACHE.get())

    def test_run_requires_an_explicit_scope(self):
        """The token map is shared across cells, so its scope cannot come from call order.

        With an optional root the map took its scope from whichever cell asked first:
        seeded from a narrow pool, every later cell silently under-counted against a map
        that never covered them — `failed_tokens_1` returning 0 instead of 96, no error.
        """
        with self.assertRaisesRegex(ValueError, "requires root_qs"), state.classification_run(root_qs=None):
            pass

    def test_unclassifiable_declares_its_own_scope(self):
        """Served standalone as a filter list, it opens the run and must set the scope."""
        source = inspect.getsource(state.unclassifiable)
        self.assertIn("classification_run(root_qs=qs)", source)

    def test_unclassifiable_is_derived_from_the_partition(self):
        """The catch-all must cover every other cell, so it reads the partition itself.

        A parallel list of cell functions beside the partition is the wrong shape here:
        add a cell, forget the list, and the balance check goes quiet instead of failing.
        """
        source = inspect.getsource(state.unclassifiable)
        self.assertIn("MATCH_JOURNEY_V5.bucket_ids()", source)
        self.assertIn("UNCLASSIFIABLE_LIST_ID", source)
        self.assertEqual(state.UNCLASSIFIABLE_LIST_ID, "match_state__unclassifiable")
        self.assertIn(state.UNCLASSIFIABLE_LIST_ID, MATCH_JOURNEY_V5.bucket_ids())

    def test_closing_kinds_and_stages_have_one_source(self):
        """The partition and the served filter lists derive from these, not from copies."""
        self.assertEqual(
            [b.list_id for phase in MATCH_JOURNEY_V5.phases if phase.id == "inactive" for b in phase.buckets],
            [f"match_state__{k}_{s}" for k in state.CLOSING_KINDS for s in state.STAGES if s != "successful"],
        )

    def test_served_list_ids_are_the_catalog(self):
        """A cell the API cannot serve is a 500 on the funnel that requests it."""
        from management.api.match_journey_filter_list import MATCH_STATE_LIST_IDS

        self.assertEqual(set(MATCH_STATE_LIST_IDS), set(CATALOG))

    def test_in_flight_is_tokens_0_through_7(self):
        in_flight = next(phase for phase in MATCH_JOURNEY_V5.phases if phase.id == "in_flight")
        self.assertEqual(
            [bucket.list_id for bucket in in_flight.buckets],
            [f"match_state__tokens_{n}" for n in range(8)],
        )
        self.assertNotIn("match_state__in_flight", MATCH_JOURNEY_V5.bucket_ids())
        self.assertEqual(CATALOG["match_state__in_flight"].role, CatalogRole.COMPOSITE)
        self.assertEqual(
            [CATALOG[f"match_state__tokens_{n}"].display_name for n in range(8)],
            [f"In flight - {n} tokens" for n in range(8)],
        )

    def test_kickoff_includes_both_contacted_no_video(self):
        kickoff = next(phase for phase in MATCH_JOURNEY_V5.phases if phase.id == "kickoff")
        self.assertIn("match_state__both_contacted_no_video", [b.list_id for b in kickoff.buckets])

    def test_success_has_engaged_dormant_and_off_platform(self):
        success = next(phase for phase in MATCH_JOURNEY_V5.phases if phase.id == "successful")
        self.assertEqual(
            [b.list_id for b in success.buckets],
            [
                "match_state__success_engaged",
                "match_state__success_dormant",
                "match_state__success_off_platform",
                "match_state__reported_successful",
                "match_state__unmatched_successful",
                "match_state__account_deleted_successful",
                "match_state__ghosted_successful",
                "match_state__unrecorded_successful",
            ],
        )

    def test_clocks(self):
        self.assertEqual(ENGAGEMENT_DAYS, 28)
        self.assertEqual(FAILURE_CLIFF_DAYS, 70)
        engagement_weeks = ENGAGEMENT_DAYS // 7
        failure_weeks = FAILURE_CLIFF_DAYS // 7
        self.assertIn(f"dormant after {engagement_weeks} weeks", MATCH_JOURNEY_V5.description)
        self.assertIn(f"failed after {failure_weeks} weeks", MATCH_JOURNEY_V5.description)

    def test_partition_cells_are_states_or_exits_only(self):
        self.assertEqual(partition_buckets_with_disallowed_roles(MATCH_JOURNEY_V5), [])


class CrossJourneyConsistencyTests(SimpleTestCase):
    """The two journeys classify the same matches; they must not disagree about success.

    They did. ``user_journey`` asked the V4 ``completed_match | match_free_play`` pair
    (the comparison-only v0 rule) while ``match_journey`` used the active v1 rule, so 381
    matches were successful to one chart and not the other — and 96 users read as
    "never succeeded" while one of their own matches read "Successful".

    Asserted on what the code *references*, not on its source text: a comment mentioning
    the old rule must not fail the test, and a call to it must.
    """

    def test_user_journey_asks_match_tokens_for_success(self):
        from management.analytics.user_journey.queries import state as ustate

        referenced = set(ustate._has_success_match.__code__.co_names)
        self.assertIn("successful_matches", referenced)
        self.assertEqual(referenced & {"completed_match", "match_free_play"}, set())

    def test_match_journey_asks_match_tokens_for_success(self):
        from management.analytics.match_journey.queries import state as mstate

        # Success is the shared token map (≥ threshold) plus off-platform — not a second
        # annotate via ``successful_match_ids``, which duplicated the LiveKit SUM on classify.
        referenced = set(mstate._successful_ids.__code__.co_names) | {
            name
            for const in mstate._successful_ids.__code__.co_consts
            if hasattr(const, "co_names")
            for name in const.co_names
        }
        self.assertIn("_tokens_map", referenced)
        self.assertIn("_success_token_threshold", referenced)
        self.assertIn("completed_off_plattform", inspect.getsource(mstate._successful_ids))
        self.assertNotIn("successful_match_ids", referenced)

    def test_both_journeys_resolve_to_one_definition(self):
        """Same underlying callables, so there is a single place to change the rule."""
        from management.analytics.match_journey.queries import state as mstate
        from management.analytics.user_journey.queries import state as ustate
        from management.match_success import match_tokens_by_id, success_token_threshold, successful_matches

        self.assertIs(mstate.match_tokens_by_id, match_tokens_by_id)
        self.assertEqual(mstate.success_token_threshold(), success_token_threshold())
        # user_journey imports lazily inside the predicate; resolve it the same way.
        from management.match_success import successful_matches as imported

        self.assertIs(imported, successful_matches)
        self.assertIs(ustate.__dict__.get("successful_matches", successful_matches), successful_matches)

    def test_off_platform_is_part_of_the_shared_definition(self):
        """Not an arm each chart bolts on — that is how the two drifted apart."""
        from management.match_success.versions.v1_total_minutes import successful_matches as v1_successful

        self.assertIn("completed_off_plattform", inspect.getsource(v1_successful))


class MatchPartitionCohortTypeTests(TestCase):
    """Match type is a cohort segment, not a partition cell (conventions §17)."""

    def _user(self, prefix):
        return User.objects.create_user(
            email=f"{prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name=prefix,
        )

    def _match(self, prefix, match_type, *, support=False):
        return Match.objects.create(
            user1=self._user(f"{prefix}-a"),
            user2=self._user(f"{prefix}-b"),
            match_type=match_type,
            support_matching=support,
            active=True,
            confirmed=False,
        )

    def _ids(self, match_type=None):
        return set(MatchPartitionCohort(match_type=match_type).apply(Match.objects.all()).values_list("id", flat=True))

    def test_unfiltered_includes_standard_and_random_call_only(self):
        standard = self._match("std", MatchType.STANDARD)
        random_call = self._match("rc", MatchType.RANDOM_CALL)
        self._match("tmp", MatchType.TEMPORARY)
        self._match("sup", MatchType.STANDARD, support=True)
        self.assertEqual(self._ids(), {standard.id, random_call.id})

    def test_standard_cohort_excludes_random_calls(self):
        standard = self._match("std", MatchType.STANDARD)
        random_call = self._match("rc", MatchType.RANDOM_CALL)
        ids = self._ids(MatchType.STANDARD)
        self.assertIn(standard.id, ids)
        self.assertNotIn(random_call.id, ids)

    def test_random_call_cohort_excludes_standard(self):
        standard = self._match("std", MatchType.STANDARD)
        random_call = self._match("rc", MatchType.RANDOM_CALL)
        ids = self._ids(MatchType.RANDOM_CALL)
        self.assertIn(random_call.id, ids)
        self.assertNotIn(standard.id, ids)

    def test_temporary_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "match_type must be one of"):
            MatchPartitionCohort(match_type=MatchType.TEMPORARY)

    def test_cohort_declares_its_entity(self):
        self.assertIs(MatchPartitionCohort().base_model, Match)


class ParseMatchTypeInputTests(SimpleTestCase):
    """``_parse_choice_input`` as used for ``match_type`` — the shared helper's other use
    (``user_type``) is covered by ``ParseUserTypeInputTests`` in
    ``test_user_journey_v5_analytics.py``."""

    def _parse(self, value):
        from management.analytics.match_journey.cohorts import JOURNEY_MATCH_TYPES
        from management.api.user_advanced_statistics import _parse_choice_input

        return _parse_choice_input(value, allowed=JOURNEY_MATCH_TYPES, field_name="match_type")

    def test_blank_values_are_unfiltered(self):
        self.assertIsNone(self._parse(None))
        self.assertIsNone(self._parse(""))
        self.assertIsNone(self._parse("  "))

    def test_known_types_are_kept(self):
        self.assertEqual(self._parse("standard"), MatchType.STANDARD)
        self.assertEqual(self._parse("random_call"), MatchType.RANDOM_CALL)

    def test_temporary_and_unknown_types_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "match_type must be"):
            self._parse("temporary")
        with self.assertRaisesRegex(ValueError, "match_type must be"):
            self._parse("organic")
        with self.assertRaisesRegex(ValueError, "match_type must be"):
            self._parse(True)
