"""V5 user journey: structural validation plus a real partition balance check.

The point of the data tests is the invariant, not the individual counts: every user in
the cohort lands in exactly one bucket. V4 reported overlaps and missing users on every
page load and nothing ever failed, so the fixtures here deliberately build the flag
combinations that produced them (conventions §13).
"""

import inspect
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from django.test import SimpleTestCase, TestCase, skipUnlessDBFeature
from django.utils import timezone

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.roles import CatalogRole
from management.analytics.registry import (
    ALL_CATALOG,
    ALL_PARTITIONS,
    DOMAIN_PREFIXES,
    assert_composite_equals_members_strict,
    assert_composites_valid_strict,
    assert_partition_balances_strict,
    assert_partition_valid_strict,
    baseline_list_id,
    composite_entries,
    compute_partition,
    get_partition,
    partition_buckets_with_disallowed_roles,
    prefixes_claimed_by_multiple_domains,
)
from management.analytics.user_journey.catalog import CATALOG as UJ_CATALOG
from management.analytics.user_journey.cohorts import PartitionCohort
from management.analytics.user_journey.funnels import SIGNUP_FUNNEL
from management.analytics.user_journey.partitions import (
    PARTITION_ALLOWED_ROLES,
    USER_JOURNEY_V5,
    PartitionBucket,
    PartitionDefinition,
    PartitionPhase,
)
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.profile import Profile
from management.models.state import State
from management.models.unconfirmed_matches import MatchType, ProposedMatch
from management.models.user import User

_A0_GERMAN = [{"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}]


class JourneyV5StructureTests(SimpleTestCase):
    def test_v5_is_registered(self):
        self.assertIn(USER_JOURNEY_V5, ALL_PARTITIONS)
        self.assertIs(get_partition("user-journey-v5"), USER_JOURNEY_V5)

    def test_v5_passes_structural_validation(self):
        assert_partition_valid_strict(USER_JOURNEY_V5)

    def test_partition_cells_are_states_or_exits_only(self):
        self.assertEqual(PARTITION_ALLOWED_ROLES, frozenset({CatalogRole.STAGE, CatalogRole.DROPOUT}))
        self.assertEqual(partition_buckets_with_disallowed_roles(USER_JOURNEY_V5), [])

    def test_phase_order_matches_the_journey(self):
        self.assertEqual(
            [phase.id for phase in USER_JOURNEY_V5.phases],
            ["signup", "pre_match", "first_match", "after_failed_first", "successful_first", "past"],
        )

    def test_no_bucket_appears_in_two_phases(self):
        bucket_ids = USER_JOURNEY_V5.bucket_ids()
        self.assertEqual(len(bucket_ids), len(set(bucket_ids)))

    def test_drill_down_lists_are_in_the_catalog_but_not_the_partition(self):
        """A list that can overlap the partition must not be a cell of it."""
        self.assertIn("state__failed_match_reasons", UJ_CATALOG)
        self.assertNotIn("state__failed_match_reasons", USER_JOURNEY_V5.bucket_ids())

    def test_partition_cells_and_funnel_steps_never_share_an_id(self):
        """The two constructs answer different questions and must not reuse an ID.

        ``funnel__email_verified`` counts everyone who ever verified;
        ``state__form_unfilled`` counts those who verified and got no further.
        A shared ID would let one be rendered as the other.
        """
        shared = set(SIGNUP_FUNNEL.list_ids()) & set(USER_JOURNEY_V5.bucket_ids())
        self.assertEqual(shared, set())

    def test_partition_cells_all_sit_in_the_state_namespace(self):
        for list_id in USER_JOURNEY_V5.bucket_ids():
            self.assertTrue(list_id.startswith("state__"), list_id)

    def test_funnel_and_partition_share_one_baseline(self):
        """`all_users` and the old `journey__all` were the same set, so there is one entry."""
        self.assertEqual(USER_JOURNEY_V5.baseline_list_id, "funnel__all")
        self.assertEqual(baseline_list_id(SIGNUP_FUNNEL), "funnel__all")

    def test_domain_declares_both_namespaces(self):
        self.assertEqual(DOMAIN_PREFIXES["user_journey"], ("funnel__", "state__"))
        self.assertEqual(prefixes_claimed_by_multiple_domains(), {})

    def test_two_domains_may_not_claim_the_same_prefix(self):
        DOMAIN_PREFIXES["match"] = ("state__",)
        try:
            self.assertEqual(prefixes_claimed_by_multiple_domains(), {"state__": ["user_journey", "match"]})
        finally:
            del DOMAIN_PREFIXES["match"]

    def test_no_bucket_carries_a_label_override(self):
        """Overrides are for chart-specific wording; their presence should be reviewable."""
        for phase in USER_JOURNEY_V5.phases:
            for bucket in phase.buckets:
                self.assertIsNone(bucket.label_override, bucket.list_id)
                self.assertIsNone(bucket.description_override, bucket.list_id)

    def test_every_catalog_entry_has_a_label_and_description(self):
        for list_id, entry in UJ_CATALOG.items():
            self.assertTrue(entry.display_name, list_id)
            self.assertTrue(entry.description, list_id)

    def test_v5_does_not_reuse_the_cumulative_signup_funnel_lists(self):
        """Stage reaches are nested; summing them as partition cells is meaningless."""
        for list_id in USER_JOURNEY_V5.bucket_ids():
            self.assertFalse(list_id.startswith("funnel__"), list_id)


class CompositeDeclarationTests(SimpleTestCase):
    """A composite is exempt from the partition-cell checks, so its members must be declared."""

    def test_every_composite_declares_usable_members(self):
        assert_composites_valid_strict()

    def test_served_list_ids_are_the_catalog(self):
        """Every catalog cell must be servable — an unservable one is a 500 on the chart.

        The IDs are listed by hand in ``user_advanced_filter_lists`` rather than derived
        from the catalog, because deriving them there imports
        ``user_journey.queries.funnel``, which imports ``management.api`` and closes an
        import cycle. So this check is the guard, alongside
        ``registry.catalog_keys_not_servable``.
        """
        from management.analytics.user_journey.catalog import CATALOG as UJ
        from management.api.user_advanced_filter_lists import FUNNEL_LIST_IDS, STATE_LIST_IDS

        self.assertEqual(set(FUNNEL_LIST_IDS) | set(STATE_LIST_IDS), set(UJ))

    def test_record_incomplete_is_a_positive_definition(self):
        """Not a complement of the other cells, so no parallel list has to be kept in step.

        The match journey's catch-all *is* a complement and needed deriving from the
        partition; this one states its own membership, which is the sturdier shape.
        """
        from management.analytics.user_journey.queries import state as ustate

        source = inspect.getsource(ustate.record_incomplete)
        self.assertIn("state__isnull=True", source)
        self.assertNotIn("exclude", source)

    def test_registered_composites(self):
        """Pinned so a new rollup is a deliberate addition, not a surprise in a chart."""
        self.assertEqual(sorted(composite_entries()), ["match_state__in_flight", "state__first_search"])

    def test_composite_members_are_all_partition_cells(self):
        """Otherwise the rollup and the chart would be counting different populations."""
        members = ALL_CATALOG["state__first_search"].members
        self.assertEqual(set(members) - set(USER_JOURNEY_V5.bucket_ids()), set())

    def test_a_composite_with_no_members_is_rejected(self):
        entry = ALL_CATALOG["state__first_search"]
        ALL_CATALOG["state__unchecked_rollup"] = replace(entry, list_id="state__unchecked_rollup", members=())
        try:
            with self.assertRaises(AssertionError):
                assert_composites_valid_strict()
        finally:
            del ALL_CATALOG["state__unchecked_rollup"]

    def test_a_composite_pointing_at_an_unknown_member_is_rejected(self):
        entry = ALL_CATALOG["state__first_search"]
        ALL_CATALOG["state__bad_rollup"] = replace(entry, list_id="state__bad_rollup", members=("state__nope",))
        try:
            with self.assertRaises(AssertionError):
                assert_composites_valid_strict()
        finally:
            del ALL_CATALOG["state__bad_rollup"]


class JourneyV5PayloadTests(SimpleTestCase):
    def test_payload_carries_labels_so_the_client_needs_none(self):
        payload = USER_JOURNEY_V5.as_payload(ALL_CATALOG)
        self.assertEqual(payload["id"], "user-journey-v5")
        self.assertEqual(payload["baseline_list_id"], "funnel__all")

        buckets = [bucket for phase in payload["phases"] for bucket in phase["buckets"]]
        self.assertEqual(len(buckets), len(USER_JOURNEY_V5.bucket_ids()))
        for bucket in buckets:
            self.assertTrue(bucket["label"])
            self.assertTrue(bucket["description"])

    def test_labels_come_from_the_catalog(self):
        payload = USER_JOURNEY_V5.as_payload(ALL_CATALOG)
        labels = {b["list_id"]: b["label"] for phase in payload["phases"] for b in phase["buckets"]}
        self.assertEqual(labels["state__onboarding_no_show"], UJ_CATALOG["state__onboarding_no_show"].display_name)
        self.assertEqual(labels["state__deleted"], UJ_CATALOG["state__deleted"].display_name)

    def test_overrides_win_over_the_catalog_when_set(self):
        partition = PartitionDefinition(
            id="test",
            title="Test",
            description="",
            base_model=User,
            baseline_list_id="funnel__all",
            phases=(
                PartitionPhase(
                    id="only",
                    title="Only",
                    buckets=(
                        PartitionBucket(
                            list_id="state__deleted",
                            label_override="Gone",
                            description_override="Chart-specific wording",
                        ),
                    ),
                ),
            ),
        )
        meta = partition.display_meta(ALL_CATALOG)
        self.assertEqual(meta["state__deleted"]["label"], "Gone")
        self.assertEqual(meta["state__deleted"]["description"], "Chart-specific wording")


class CatalogAsOfTests(SimpleTestCase):
    """``as_of`` has to reach the queries, or it is decoration (conventions §10).

    Without this, each of the 30 buckets calls ``timezone.now()`` for itself and a booking
    expiring mid-request lands in ``state__onboarding_booked`` for one query and
    ``state__onboarding_no_show`` for another — a self-inflicted partition overlap.
    """

    def test_time_dependent_entries_are_detected_from_the_signature(self):
        self.assertTrue(ALL_CATALOG["state__onboarding_booked"].is_time_dependent)
        self.assertTrue(ALL_CATALOG["state__onboarding_no_show"].is_time_dependent)

    def test_entries_that_do_not_take_as_of_are_not_flagged(self):
        self.assertFalse(ALL_CATALOG["state__deleted"].is_time_dependent)
        self.assertFalse(ALL_CATALOG["funnel__all"].is_time_dependent)

    def test_build_forwards_as_of_to_time_dependent_queries(self):
        seen = {}

        def query(qs, as_of=None):
            seen["as_of"] = as_of
            return qs

        entry = CatalogEntry(
            list_id="state__probe",
            role=CatalogRole.STAGE,
            queryset=query,
            description="",
            display_name="Probe",
            base_model=User,
        )
        moment = timezone.now()
        entry.build(User.objects.none(), as_of=moment)
        self.assertEqual(seen["as_of"], moment)

    def test_build_does_not_pass_as_of_to_queries_that_cannot_take_it(self):
        """A uniform call would break every list shared with the panel's filter lists."""

        def query(qs):
            return qs

        entry = CatalogEntry(
            list_id="state__probe",
            role=CatalogRole.STAGE,
            queryset=query,
            description="",
            display_name="Probe",
            base_model=User,
        )
        # Would raise TypeError if `as_of` were forwarded blindly.
        entry.build(User.objects.none(), as_of=timezone.now())

    def test_every_time_dependent_bucket_is_reachable_with_as_of(self):
        """Any bucket that reads the clock must be able to be pinned to the run's instant."""
        for list_id in USER_JOURNEY_V5.all_list_ids():
            entry = ALL_CATALOG[list_id]
            if entry.is_time_dependent:
                self.assertIn("as_of", entry.queryset.__code__.co_varnames)


class PartitionValidationRejectsBadDefinitionsTests(SimpleTestCase):
    """Negative side of the validation — without these, "all green" proves nothing."""

    def _partition(self, *bucket_ids, baseline="funnel__all", base_model=User):
        return PartitionDefinition(
            id="test",
            title="Test",
            description="",
            base_model=base_model,
            baseline_list_id=baseline,
            phases=(
                PartitionPhase(
                    id="only",
                    title="Only",
                    buckets=tuple(PartitionBucket(list_id=bid) for bid in bucket_ids),
                ),
            ),
        )

    def test_bucket_missing_from_catalog_raises(self):
        with self.assertRaisesRegex(AssertionError, "missing from catalog"):
            assert_partition_valid_strict(self._partition("state__does_not_exist"))

    def test_segment_role_bucket_raises(self):
        """The V4 failure mode: `too_low_german_level` is a trait, so it overlapped everything."""
        with self.assertRaisesRegex(AssertionError, "disallowed roles"):
            assert_partition_valid_strict(self._partition("journey_v2__too_low_german_level"))

    def test_baseline_role_bucket_raises(self):
        with self.assertRaisesRegex(AssertionError, "disallowed roles"):
            assert_partition_valid_strict(self._partition("funnel__all"))

    def test_mismatched_base_model_raises(self):
        with self.assertRaisesRegex(AssertionError, "mismatched base_model"):
            assert_partition_valid_strict(self._partition("state__deleted", base_model=Match))

    def test_non_baseline_baseline_raises(self):
        with self.assertRaisesRegex(AssertionError, "has role"):
            assert_partition_valid_strict(self._partition("state__deleted", baseline="state__email_unverified"))

    def test_duplicated_bucket_raises(self):
        with self.assertRaisesRegex(AssertionError, "same bucket twice"):
            assert_partition_valid_strict(self._partition("state__deleted", "state__deleted"))


@skipUnlessDBFeature("supports_json_field_contains")
class JourneyV5PartitionBalanceTests(TestCase):
    """Every cohort user lands in exactly one bucket, including the awkward ones.

    Postgres only: the eligibility rules read German level out of ``Profile.lang_skill``
    with a JSON ``contains`` lookup, which SQLite cannot execute. Local SQLite runs skip
    this class; the structural tests above still cover the definition.
    """

    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        builders = (
            cls._signup_users,
            cls._active_users,
            cls._success_users,
            cls._lapsed_users,
            cls._past_users,
            cls._pathological_users,
        )
        for build in builders:
            build.__func__(cls)

    # -- fixture helpers ---------------------------------------------------

    @classmethod
    def _user(cls, key, *, joined_days_ago=5, is_active=True, user_type=None, state=None, profile=None):
        user = User.objects.create_user(
            email=f"{key}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name=key,
        )
        if state:
            State.objects.filter(user=user).update(**state)
        profile_updates = dict(profile or {})
        if user_type is not None:
            profile_updates["user_type"] = user_type
        if profile_updates:
            Profile.objects.filter(user=user).update(**profile_updates)
        # date_joined is set on insert, so it has to be written back (conventions §13).
        User.objects.filter(pk=user.pk).update(
            is_active=is_active,
            date_joined=timezone.now() - timedelta(days=joined_days_ago),
        )
        user.refresh_from_db()
        cls.users[key] = user
        return user

    @classmethod
    def _onboarded(cls, key, *, searching=True, **kwargs):
        state = {
            "user_form_state": State.UserFormStateChoices.FILLED,
            "email_authenticated": True,
            "is_onboarded": True,
            "searching_state": (
                State.SearchingStateChoices.SEARCHING if searching else State.SearchingStateChoices.IDLE
            ),
        }
        state.update(kwargs.pop("state", {}))
        return cls._user(key, state=state, **kwargs)

    @classmethod
    def _appointment(cls, user, *, days_from_now):
        moment = timezone.now() + timedelta(days=days_from_now)
        PreMatchingAppointment.objects.create(user=user, start_time=moment, end_time=moment)

    @classmethod
    def _match(cls, user1, user2, *, created_days_ago=1, **fields):
        match = Match.objects.create(user1=user1, user2=user2, support_matching=False, **fields)
        Match.objects.filter(pk=match.pk).update(created_at=timezone.now() - timedelta(days=created_days_ago))
        return match

    # -- fixtures ----------------------------------------------------------

    @classmethod
    def _signup_users(cls):
        cls._user("signup_created")
        cls._user("signup_email_verified", state={"email_authenticated": True})
        cls._user(
            "signup_form_completed",
            user_type=Profile.TypeChoices.VOLUNTEER,
            state={"user_form_state": State.UserFormStateChoices.FILLED, "email_authenticated": True},
        )
        cls._user(
            "signup_self_onboarding",
            user_type=Profile.TypeChoices.VOLUNTEER,
            state={
                "user_form_state": State.UserFormStateChoices.FILLED,
                "email_authenticated": True,
                "self_onboarding_started": True,
                "self_onboarding_completed": False,
            },
        )
        booked = cls._user(
            "signup_onboarding_booked",
            user_type=Profile.TypeChoices.VOLUNTEER,
            state={"user_form_state": State.UserFormStateChoices.FILLED, "email_authenticated": True},
        )
        cls._appointment(booked, days_from_now=3)

        no_show = cls._user(
            "signup_no_show",
            user_type=Profile.TypeChoices.VOLUNTEER,
            state={"user_form_state": State.UserFormStateChoices.FILLED, "email_authenticated": True},
        )
        cls._appointment(no_show, days_from_now=-3)

        cls._user(
            "signup_ineligible_a0",
            user_type=Profile.TypeChoices.LEARNER,
            profile={"lang_skill": _A0_GERMAN, "country_of_residence": Profile.CountryChoices.GERMANY},
            state={"user_form_state": State.UserFormStateChoices.FILLED, "email_authenticated": True},
        )
        cls._user(
            "signup_ineligible_abroad",
            user_type=Profile.TypeChoices.LEARNER,
            profile={"country_of_residence": Profile.CountryChoices.AUSTRIA},
            state={"user_form_state": State.UserFormStateChoices.FILLED, "email_authenticated": True},
        )

    @classmethod
    def _proposal(cls, user1, user2, *, created_days_ago=1, **fields):
        """A resolved proposal. ``potential_matching_created_at`` is ``auto_now_add``, so it
        has to be written back after insert for the most-recent tiebreak to be testable."""
        proposal = ProposedMatch.objects.create(user1=user1, user2=user2, **{"confirming_user": user2, **fields})
        ProposedMatch.objects.filter(pk=proposal.pk).update(
            potential_matching_created_at=timezone.now() - timedelta(days=created_days_ago)
        )
        return proposal

    @classmethod
    def _active_users(cls):
        cls._onboarded("active_first_search", joined_days_ago=5, user_type=Profile.TypeChoices.VOLUNTEER)
        cls._onboarded(
            "active_search_blocked",
            joined_days_ago=5,
            user_type=Profile.TypeChoices.LEARNER,
            profile={"lang_skill": _A0_GERMAN, "country_of_residence": Profile.CountryChoices.GERMANY},
        )

        proposer = cls._onboarded("active_proposed", user_type=Profile.TypeChoices.VOLUNTEER)
        partner = cls._onboarded("proposal_partner", user_type=Profile.TypeChoices.LEARNER)
        ProposedMatch.objects.create(
            user1=proposer,
            user2=partner,
            closed=False,
            expires_at=timezone.now() + timedelta(days=3),
        )

        takeoff = cls._onboarded("first_match_kickoff", user_type=Profile.TypeChoices.VOLUNTEER)
        takeoff_partner = cls._onboarded("kickoff_partner", user_type=Profile.TypeChoices.LEARNER)
        cls._match(takeoff, takeoff_partner, active=True, confirmed=False, created_days_ago=2)

        ongoing = cls._onboarded("first_match_ongoing", user_type=Profile.TypeChoices.VOLUNTEER)
        ongoing_partner = cls._onboarded("ongoing_partner", user_type=Profile.TypeChoices.LEARNER)
        cls._match(
            ongoing,
            ongoing_partner,
            active=True,
            confirmed=True,
            created_days_ago=14,
            total_messages_counter=6,
            total_mutal_video_calls_counter=2,
            latest_interaction_at=timezone.now() - timedelta(days=1),
        )

        again = cls._onboarded("searching_after_failed", user_type=Profile.TypeChoices.VOLUNTEER)
        again_partner = cls._onboarded(
            "searching_after_failed_partner", searching=False, user_type=Profile.TypeChoices.LEARNER
        )
        cls._match(again, again_partner, active=False, confirmed=True, created_days_ago=60)

        rematch = cls._onboarded("rematch_proposed", user_type=Profile.TypeChoices.VOLUNTEER)
        rematch_old = cls._onboarded("rematch_old_partner", searching=False, user_type=Profile.TypeChoices.LEARNER)
        rematch_new = cls._onboarded("rematch_proposal_partner", user_type=Profile.TypeChoices.LEARNER)
        cls._match(rematch, rematch_old, active=False, confirmed=False, created_days_ago=40)
        ProposedMatch.objects.create(
            user1=rematch,
            user2=rematch_new,
            closed=False,
            expires_at=timezone.now() + timedelta(days=3),
        )

        cls._first_search_users()

    @classmethod
    def _first_search_users(cls):
        """The five ways a first search can look, all invisible to V4.

        ``matching_proposals()`` only sees open proposals, so a user whose proposal was
        rejected or expired looked identical to one nobody had ever been proposed to.
        Each pair below is two users in one proposal, which is also how the two rejection
        cells get covered: the same row is "they rejected it" from one side and "the
        partner rejected them" from the other.
        """
        rejecter = cls._onboarded("first_search_rejected_by_them", user_type=Profile.TypeChoices.LEARNER)
        rejected = cls._onboarded("first_search_rejected_by_partner", user_type=Profile.TypeChoices.VOLUNTEER)
        cls._proposal(rejected, rejecter, confirming_user=rejecter, closed=True, rejected=True, rejected_by=rejecter)

        expired_a = cls._onboarded("first_search_expired", user_type=Profile.TypeChoices.VOLUNTEER)
        expired_b = cls._onboarded("first_search_expired_partner", user_type=Profile.TypeChoices.LEARNER)
        cls._proposal(expired_a, expired_b, closed=True, expired=True, expires_at=timezone.now() - timedelta(days=1))

        closed_a = cls._onboarded("first_search_closed", user_type=Profile.TypeChoices.VOLUNTEER)
        closed_b = cls._onboarded("first_search_closed_partner", user_type=Profile.TypeChoices.LEARNER)
        cls._proposal(closed_a, closed_b, closed=True)

        # Two resolved proposals of different kinds: the more recent one decides.
        tiebreak = cls._onboarded("first_search_latest_proposal_wins", user_type=Profile.TypeChoices.VOLUNTEER)
        old_partner = cls._onboarded("first_search_tiebreak_old_partner", user_type=Profile.TypeChoices.LEARNER)
        new_partner = cls._onboarded("first_search_tiebreak_new_partner", user_type=Profile.TypeChoices.LEARNER)
        cls._proposal(
            tiebreak,
            old_partner,
            created_days_ago=30,
            confirming_user=tiebreak,
            closed=True,
            rejected=True,
            rejected_by=tiebreak,
        )
        cls._proposal(tiebreak, new_partner, created_days_ago=2, closed=True, expired=True, expires_at=timezone.now())

        # Random-call proposals are a different product surface and must not classify a
        # matching-funnel bucket.
        rc_a = cls._onboarded("first_search_random_call_only", user_type=Profile.TypeChoices.VOLUNTEER)
        rc_b = cls._onboarded("first_search_random_call_partner", user_type=Profile.TypeChoices.LEARNER)
        cls._proposal(rc_a, rc_b, closed=True, rejected=True, rejected_by=rc_b, match_type=MatchType.RANDOM_CALL)

    @classmethod
    def _success_users(cls):
        # Completed flag, no live activity → idle success cell.
        completed = cls._onboarded("success_idle", searching=False, user_type=Profile.TypeChoices.VOLUNTEER)
        completed_partner = cls._onboarded(
            "success_idle_partner", searching=False, user_type=Profile.TypeChoices.LEARNER
        )
        cls._match(completed, completed_partner, active=True, confirmed=True, completed=True, created_days_ago=90)

        # Free-play still counts as live → settled success cell.
        free_play = cls._onboarded("success_ongoing_settled", searching=False, user_type=Profile.TypeChoices.VOLUNTEER)
        free_play_partner = cls._onboarded(
            "success_ongoing_settled_partner", searching=False, user_type=Profile.TypeChoices.LEARNER
        )
        cls._match(
            free_play,
            free_play_partner,
            active=True,
            confirmed=True,
            created_days_ago=100,
            total_messages_counter=20,
            total_mutal_video_calls_counter=8,
            latest_interaction_at=timezone.now() - timedelta(days=2),
        )

        # Successful then searching again with nothing live.
        searching = cls._onboarded("success_searching", user_type=Profile.TypeChoices.VOLUNTEER)
        searching_partner = cls._onboarded(
            "success_searching_partner", searching=False, user_type=Profile.TypeChoices.LEARNER
        )
        cls._match(searching, searching_partner, active=False, confirmed=True, completed=True, created_days_ago=95)

        # Successful, still live, and searching for another.
        both = cls._onboarded("success_ongoing_searching", user_type=Profile.TypeChoices.VOLUNTEER)
        both_done = cls._onboarded(
            "success_ongoing_searching_done", searching=False, user_type=Profile.TypeChoices.LEARNER
        )
        both_live = cls._onboarded("success_ongoing_searching_live", user_type=Profile.TypeChoices.LEARNER)
        cls._match(both, both_done, active=True, confirmed=True, completed=True, created_days_ago=95)
        cls._match(
            both,
            both_live,
            active=True,
            confirmed=True,
            created_days_ago=14,
            total_messages_counter=6,
            total_mutal_video_calls_counter=2,
            latest_interaction_at=timezone.now() - timedelta(days=1),
        )

    @classmethod
    def _lapsed_users(cls):
        # Long-waiting first searcher — still pre-match, not a separate time-based bucket.
        cls._onboarded("first_search_long_waiting", joined_days_ago=120, user_type=Profile.TypeChoices.VOLUNTEER)
        cls._onboarded("lapsed_gave_up", searching=False, user_type=Profile.TypeChoices.VOLUNTEER)

        failed = cls._onboarded("stopped_after_failed", searching=False, user_type=Profile.TypeChoices.VOLUNTEER)
        failed_partner = cls._onboarded(
            "stopped_after_failed_partner", searching=False, user_type=Profile.TypeChoices.LEARNER
        )
        cls._match(failed, failed_partner, active=False, confirmed=False, created_days_ago=40)

    @classmethod
    def _past_users(cls):
        cls._user("past_unresponsive", state={"unresponsive": True})
        cls._user("past_deleted", is_active=False)

        # Seen in the real data: a live account with no state row at all. Every other
        # live bucket filters on `state__*`, so without its own bucket it is unclassifiable.
        stateless = cls._user("record_incomplete")
        State.objects.filter(user=stateless).delete()

        gone = cls._user("past_deleted_after_success", is_active=False)
        gone_partner = cls._onboarded("gone_partner", searching=False, user_type=Profile.TypeChoices.LEARNER)
        cls._match(gone, gone_partner, active=True, confirmed=True, completed=True, created_days_ago=95)

    @classmethod
    def _pathological_users(cls):
        """Flag combinations that broke V4. Each one is a bucket boundary, not a happy path."""
        # A0 learner with a call booked: counted in `booked_onboarding_call` *and*
        # `too_low_german_level` under V4, because only the former skipped the A0 exclusion.
        a0_booked = cls._user(
            "a0_learner_with_booked_call",
            user_type=Profile.TypeChoices.LEARNER,
            profile={"lang_skill": _A0_GERMAN, "country_of_residence": Profile.CountryChoices.GERMANY},
            state={"user_form_state": State.UserFormStateChoices.FILLED, "email_authenticated": True},
        )
        cls._appointment(a0_booked, days_from_now=2)

        # No-show who rebooked: V4's `booked_onboarding_call` excluded everyone matching
        # `no_show`, so a rebooked user was reported as a no-show.
        rebooked = cls._user(
            "no_show_who_rebooked",
            user_type=Profile.TypeChoices.VOLUNTEER,
            state={"user_form_state": State.UserFormStateChoices.FILLED, "email_authenticated": True},
        )
        cls._appointment(rebooked, days_from_now=-5)
        cls._appointment(rebooked, days_from_now=4)

        # Marked onboarded by a backfill while the form is still unfilled. Gating the
        # signup phase on `is_onboarded=False` alone would drop this user entirely.
        cls._user(
            "onboarded_with_unfilled_form",
            state={"email_authenticated": True, "is_onboarded": True},
        )

        # Learner who never answered the residence question. V4's negated country filter
        # matched NULL, so they were silently treated as living outside Germany.
        cls._onboarded(
            "learner_without_country",
            user_type=Profile.TypeChoices.LEARNER,
            profile={"country_of_residence": None},
        )

        # Holds a completed match and a live ongoing one. V4 excluded them from both
        # `happy_inactive` and `ongoing_non_completed_match`, so they vanished.
        both = cls._onboarded("completed_and_ongoing", searching=False, user_type=Profile.TypeChoices.VOLUNTEER)
        both_partner_a = cls._onboarded("both_partner_a", searching=False, user_type=Profile.TypeChoices.LEARNER)
        both_partner_b = cls._onboarded("both_partner_b", searching=False, user_type=Profile.TypeChoices.LEARNER)
        cls._match(both, both_partner_a, active=True, confirmed=True, completed=True, created_days_ago=95)
        cls._match(
            both,
            both_partner_b,
            active=True,
            confirmed=True,
            created_days_ago=14,
            total_messages_counter=6,
            total_mutal_video_calls_counter=2,
            latest_interaction_at=timezone.now() - timedelta(days=1),
        )

        # Unresponsive but successful. V4 counted them in `marked_unresponsive` *and*
        # `happy_inactive`, because the success buckets had no state gate.
        unresponsive = cls._user("unresponsive_with_completed_match", state={"unresponsive": True})
        unresponsive_partner = cls._onboarded(
            "unresponsive_partner", searching=False, user_type=Profile.TypeChoices.LEARNER
        )
        cls._match(unresponsive, unresponsive_partner, active=True, confirmed=True, completed=True, created_days_ago=95)

        # Self-onboarding started and no call booked: matched both
        # `journey_v2__user_form_completed` and `journey_v2__self_onboarding_started`.
        cls._user(
            "self_onboarding_no_booking",
            user_type=Profile.TypeChoices.VOLUNTEER,
            state={
                "user_form_state": State.UserFormStateChoices.FILLED,
                "email_authenticated": True,
                "self_onboarding_started": True,
                "self_onboarding_completed": False,
            },
        )

    # -- helpers -----------------------------------------------------------

    def _cohort(self):
        return PartitionCohort(start_date="2000-01-01", end_date=timezone.now().date()).apply(User.objects.all())

    def _members_by_bucket(self):
        """Every bucket's member IDs, computed once per test.

        The obvious version — ask each bucket whether it contains one user — costs a query
        per bucket per user, and the bucket queries are subquery-heavy. Asking each bucket
        once and answering the per-user question in Python turns the placement tests from
        thousands of queries into twenty-odd.
        """
        if not hasattr(self, "_bucket_members"):
            cohort = self._cohort()
            self._bucket_members = {
                list_id: set(ALL_CATALOG[list_id].queryset(cohort).values_list("id", flat=True))
                for list_id in USER_JOURNEY_V5.bucket_ids()
            }
        return self._bucket_members

    def _bucket_of(self, key):
        user_id = self.users[key].id
        return [list_id for list_id, member_ids in self._members_by_bucket().items() if user_id in member_ids]

    # -- the invariant -----------------------------------------------------

    def test_partition_balances_over_every_fixture(self):
        assert_partition_balances_strict(USER_JOURNEY_V5, self._cohort())

    def test_counts_sum_to_the_baseline(self):
        result = compute_partition(USER_JOURNEY_V5, self._cohort())
        self.assertTrue(result["balanced"], result)
        self.assertEqual(result["summed_count"], result["baseline_count"])
        self.assertEqual(result["baseline_count"], User.objects.count())

    def test_every_user_is_in_exactly_one_bucket(self):
        for key in self.users:
            self.assertEqual(len(self._bucket_of(key)), 1, f"{key} → {self._bucket_of(key)}")

    # -- placement of the cases V4 got wrong -------------------------------

    def test_a0_learner_with_a_booked_call_counts_as_booked_only(self):
        self.assertEqual(self._bucket_of("a0_learner_with_booked_call"), ["state__onboarding_booked"])

    def test_rebooked_no_show_counts_as_booked_not_no_show(self):
        self.assertEqual(self._bucket_of("no_show_who_rebooked"), ["state__onboarding_booked"])

    def test_self_onboarding_without_a_booking_is_not_also_form_completed(self):
        self.assertEqual(self._bucket_of("self_onboarding_no_booking"), ["state__self_onboarding"])

    def test_onboarded_with_unfilled_form_stays_in_the_signup_phase(self):
        self.assertEqual(self._bucket_of("onboarded_with_unfilled_form"), ["state__form_unfilled"])

    def test_learner_without_a_country_is_not_treated_as_living_abroad(self):
        self.assertEqual(self._bucket_of("learner_without_country"), ["state__first_search_no_proposal"])

    def test_completed_and_ongoing_counts_as_success_settled(self):
        self.assertEqual(self._bucket_of("completed_and_ongoing"), ["state__success_ongoing_settled"])

    def test_unresponsive_after_success_is_split_from_plain_unresponsive(self):
        self.assertEqual(
            self._bucket_of("unresponsive_with_completed_match"),
            ["state__unresponsive_after_success"],
        )
        self.assertEqual(self._bucket_of("past_unresponsive"), ["state__unresponsive"])

    def test_deleted_after_success_is_split_from_plain_deletion(self):
        self.assertEqual(self._bucket_of("past_deleted_after_success"), ["state__deleted_after_success"])
        self.assertEqual(self._bucket_of("past_deleted"), ["state__deleted"])

    def test_blocked_searcher_has_a_bucket_of_their_own(self):
        self.assertEqual(self._bucket_of("active_search_blocked"), ["state__search_blocked"])

    def test_long_waiting_searcher_stays_in_first_search(self):
        self.assertEqual(self._bucket_of("first_search_long_waiting"), ["state__first_search_no_proposal"])

    def test_stopped_searching_sits_in_pre_match(self):
        self.assertEqual(self._bucket_of("lapsed_gave_up"), ["state__gave_up"])
        pre_match = next(phase for phase in USER_JOURNEY_V5.phases if phase.id == "pre_match")
        self.assertIn("state__gave_up", [bucket.list_id for bucket in pre_match.buckets])

    def test_account_without_a_state_row_has_a_bucket_of_its_own(self):
        self.assertEqual(self._bucket_of("record_incomplete"), ["state__record_incomplete"])

    def test_ineligible_learners_land_in_the_ineligible_bucket(self):
        self.assertEqual(self._bucket_of("signup_ineligible_a0"), ["state__onboarding_ineligible"])
        self.assertEqual(self._bucket_of("signup_ineligible_abroad"), ["state__onboarding_ineligible"])

    # -- first-match KPI placement -----------------------------------------

    def test_open_proposal_before_any_match_is_pre_match(self):
        self.assertEqual(self._bucket_of("active_proposed"), ["state__proposed"])
        self.assertEqual(self._bucket_of("proposal_partner"), ["state__proposed"])

    def test_first_match_in_flight_cells(self):
        self.assertEqual(self._bucket_of("first_match_kickoff"), ["state__first_match_kickoff"])
        self.assertEqual(self._bucket_of("kickoff_partner"), ["state__first_match_kickoff"])
        self.assertEqual(self._bucket_of("first_match_ongoing"), ["state__first_match_ongoing"])
        self.assertEqual(self._bucket_of("ongoing_partner"), ["state__first_match_ongoing"])

    def test_after_failed_first_cells(self):
        self.assertEqual(self._bucket_of("rematch_proposed"), ["state__rematch_proposed"])
        self.assertEqual(self._bucket_of("searching_after_failed"), ["state__searching_after_failed"])
        self.assertEqual(
            self._bucket_of("searching_after_failed_partner"),
            ["state__stopped_after_failed"],
        )
        self.assertEqual(self._bucket_of("stopped_after_failed"), ["state__stopped_after_failed"])

    def test_successful_first_match_two_by_two(self):
        self.assertEqual(self._bucket_of("success_ongoing_searching"), ["state__success_ongoing_searching"])
        self.assertEqual(self._bucket_of("success_ongoing_settled"), ["state__success_ongoing_settled"])
        self.assertEqual(self._bucket_of("success_searching"), ["state__success_searching"])
        self.assertEqual(self._bucket_of("success_idle"), ["state__success_idle"])

    # -- first search, split by the last proposal's outcome ----------------

    def test_first_search_without_any_proposal(self):
        self.assertEqual(self._bucket_of("active_first_search"), ["state__first_search_no_proposal"])

    def test_rejection_is_attributed_to_the_side_that_rejected(self):
        self.assertEqual(
            self._bucket_of("first_search_rejected_by_them"),
            ["state__first_search_rejected_by_them"],
        )
        self.assertEqual(
            self._bucket_of("first_search_rejected_by_partner"),
            ["state__first_search_rejected_by_partner"],
        )

    def test_expired_proposal_is_not_reported_as_never_proposed(self):
        for key in ("first_search_expired", "first_search_expired_partner"):
            self.assertEqual(self._bucket_of(key), ["state__first_search_proposal_expired"], key)

    def test_proposal_closed_without_a_decision_is_not_reported_as_expired(self):
        for key in ("first_search_closed", "first_search_closed_partner"):
            self.assertEqual(self._bucket_of(key), ["state__first_search_proposal_closed"], key)

    def test_the_most_recent_proposal_decides(self):
        # Rejected 30 days ago, expired 2 days ago — the expiry is the current story.
        self.assertEqual(
            self._bucket_of("first_search_latest_proposal_wins"),
            ["state__first_search_proposal_expired"],
        )

    def test_random_call_proposals_do_not_classify_the_matching_funnel(self):
        for key in ("first_search_random_call_only", "first_search_random_call_partner"):
            self.assertEqual(self._bucket_of(key), ["state__first_search_no_proposal"], key)

    def test_the_five_cells_sum_back_to_the_composite(self):
        assert_composite_equals_members_strict("state__first_search", self._cohort())

    def test_composite_is_not_itself_a_partition_cell(self):
        self.assertNotIn("state__first_search", USER_JOURNEY_V5.bucket_ids())


class PartitionImbalanceIsReportedNotRaisedTests(TestCase):
    """A broken partition must surface on a GET, not 500 the page (conventions §8)."""

    def _user(self, prefix):
        return User.objects.create_user(
            email=f"{prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )

    def test_overlapping_buckets_are_reported_with_balanced_false(self):
        self._user("dup")

        overlapping = PartitionDefinition(
            id="test-overlap",
            title="Test",
            description="",
            base_model=User,
            baseline_list_id="funnel__all",
            phases=(
                PartitionPhase(
                    id="only",
                    title="Only",
                    buckets=(
                        PartitionBucket(list_id="state__email_unverified"),
                        PartitionBucket(list_id="state__duplicate_of_created"),
                    ),
                ),
            ),
        )
        duplicate = CatalogEntry(
            list_id="state__duplicate_of_created",
            role=CatalogRole.STAGE,
            queryset=UJ_CATALOG["state__email_unverified"].queryset,
            description="Same membership under a second ID.",
            display_name="Duplicate",
            base_model=User,
        )
        ALL_CATALOG["state__duplicate_of_created"] = duplicate
        try:
            with self.assertLogs("management.analytics.registry", level="WARNING"):
                result = compute_partition(overlapping, User.objects.all())
        finally:
            del ALL_CATALOG["state__duplicate_of_created"]

        self.assertFalse(result["balanced"])
        self.assertEqual(
            list(result["overlap_counts"]),
            ["state__email_unverified---state__duplicate_of_created"],
        )
        self.assertEqual(result["counts"]["state__email_unverified"], 1)

    def test_uncovered_users_are_reported_with_balanced_false(self):
        verified = self._user("uncovered")
        State.objects.filter(user=verified).update(email_authenticated=True)

        # Only covers unverified signups, so the verified user above belongs nowhere.
        incomplete = PartitionDefinition(
            id="test-incomplete",
            title="Test",
            description="",
            base_model=User,
            baseline_list_id="funnel__all",
            phases=(
                PartitionPhase(
                    id="only",
                    title="Only",
                    buckets=(PartitionBucket(list_id="state__email_unverified"),),
                ),
            ),
        )
        with self.assertLogs("management.analytics.registry", level="WARNING"):
            result = compute_partition(incomplete, User.objects.all())

        self.assertFalse(result["balanced"])
        self.assertEqual(result["uncovered_count"], 1)
        with self.assertRaisesRegex(AssertionError, "does not balance"):
            assert_partition_balances_strict(incomplete, User.objects.all())
