from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.display_time import (
    DISPLAY_TIMEZONE,
    end_of_day_inclusive,
    inclusive_range,
    parse_end_bound,
    start_of_day,
    today,
)
from management.analytics.core.funnels import (
    FUNNEL_ALLOWED_ROLES,
    FunnelDefinition,
    FunnelMergeGroup,
    FunnelMode,
    FunnelStep,
)
from management.analytics.core.roles import CatalogRole
from management.analytics.registry import (
    ALL_CATALOG,
    LEGACY_ALIASES,
    assert_all_domains_strict,
    assert_funnel_valid_strict,
    baseline_list_id,
    catalog_keys_disagreeing_with_filter_lists,
    catalog_keys_not_servable,
    catalog_keys_with_duplicated_description,
    funnel_steps_with_disallowed_roles,
    is_baseline,
    resolve_list_id,
)
from management.analytics.user_journey.catalog import CATALOG
from management.analytics.user_journey.cohorts import SignupCohort, apply_cohort
from management.analytics.user_journey.funnels import SIGNUP_FUNNEL
from management.models.matches import Match
from management.models.user import User


class AnalyticsRegistryValidationTests(SimpleTestCase):
    """The one test every registered domain inherits (conventions §8)."""

    def test_all_domains_pass_registry_validation(self):
        assert_all_domains_strict()

    def test_every_catalog_key_and_legacy_alias_is_servable(self):
        self.assertEqual(catalog_keys_not_servable(), [])

    def test_catalog_and_filter_lists_agree_on_querysets(self):
        self.assertEqual(catalog_keys_disagreeing_with_filter_lists(), [])

    def test_no_filter_list_duplicates_a_catalog_owned_description(self):
        self.assertEqual(catalog_keys_with_duplicated_description(), [])


class RegistryValidationRejectsBadFunnelsTests(SimpleTestCase):
    """Negative side of the validation. Without these, "all green" proves nothing."""

    def _entry(self, list_id, role=CatalogRole.STAGE, base_model=User):
        return CatalogEntry(
            list_id=list_id,
            role=role,
            queryset=lambda qs: qs,
            description="",
            display_name=list_id,
            base_model=base_model,
        )

    def test_step_missing_from_catalog_raises(self):
        funnel = FunnelDefinition(
            id="test",
            title="Test",
            mode=FunnelMode.STAGE,
            base_model=User,
            steps=(FunnelStep(list_id="funnel__all"), FunnelStep(list_id="funnel__does_not_exist")),
        )
        with self.assertRaisesRegex(AssertionError, "missing from catalog"):
            assert_funnel_valid_strict(funnel)

    def test_missing_step_does_not_raise_keyerror_in_role_check(self):
        """A typo'd step must surface as a readable list, not a KeyError from a dict index."""
        funnel = FunnelDefinition(
            id="test",
            title="Test",
            mode=FunnelMode.STAGE,
            base_model=User,
            steps=(FunnelStep(list_id="funnel__does_not_exist"),),
        )
        self.assertEqual(funnel_steps_with_disallowed_roles(funnel), [])

    def test_segment_role_step_raises(self):
        funnel = FunnelDefinition(
            id="test",
            title="Test",
            mode=FunnelMode.STAGE,
            base_model=User,
            steps=(FunnelStep(list_id="funnel__all"), FunnelStep(list_id="journey_v2__too_low_german_level")),
        )
        with self.assertRaisesRegex(AssertionError, "disallowed roles"):
            assert_funnel_valid_strict(funnel)

    def test_mismatched_base_model_raises(self):
        """A User list wired into a Match funnel produces a plausible, wrong number (§2)."""
        funnel = FunnelDefinition(
            id="test",
            title="Test",
            mode=FunnelMode.STAGE,
            base_model=Match,
            steps=(FunnelStep(list_id="funnel__all"),),
        )
        with self.assertRaisesRegex(AssertionError, "mismatched base_model"):
            assert_funnel_valid_strict(funnel)

    def test_funnel_without_baseline_raises(self):
        funnel = FunnelDefinition(
            id="test",
            title="Test",
            mode=FunnelMode.STAGE,
            base_model=User,
            steps=(FunnelStep(list_id="funnel__onboarded"),),
        )
        with self.assertRaisesRegex(AssertionError, "exactly one baseline"):
            assert_funnel_valid_strict(funnel)


class LegacyAliasTests(SimpleTestCase):
    """Aliases are intentionally empty — renames update callers, they do not accumulate."""

    def test_resolve_is_identity(self):
        self.assertEqual(resolve_list_id("funnel__all"), "funnel__all")
        self.assertEqual(resolve_list_id("unknown"), "unknown")

    def test_no_aliases_are_registered(self):
        self.assertEqual(LEGACY_ALIASES, {})

    def test_is_baseline_uses_the_canonical_id_only(self):
        baseline = baseline_list_id(SIGNUP_FUNNEL)
        self.assertEqual(baseline, "funnel__all")
        self.assertTrue(is_baseline("funnel__all", baseline))
        self.assertFalse(is_baseline("all", baseline))
        self.assertFalse(is_baseline("funnel__onboarded", baseline))


class SignupFunnelAnalyticsStructureTests(SimpleTestCase):
    def test_funnel_is_stage_mode(self):
        self.assertEqual(SIGNUP_FUNNEL.mode, FunnelMode.STAGE)

    def test_funnel_list_ids_order(self):
        self.assertEqual(
            SIGNUP_FUNNEL.list_ids(),
            [
                "funnel__all",
                "funnel__active_adjusted",
                "funnel__email_verified",
                "funnel__form_completed",
                "funnel__eligible_for_onboarding",
                "funnel__onboarding_started",
                "funnel__onboarded",
            ],
        )

    def test_funnel_allows_only_baseline_and_stage(self):
        self.assertEqual(
            FUNNEL_ALLOWED_ROLES,
            frozenset({CatalogRole.BASELINE, CatalogRole.STAGE}),
        )
        self.assertEqual(funnel_steps_with_disallowed_roles(SIGNUP_FUNNEL), [])

    def test_ineligibility_subsets_in_catalog_not_in_funnel(self):
        for list_id in (
            "funnel__ineligible_a0_german",
            "funnel__ineligible_outside_germany",
            "funnel__ineligible_for_onboarding",
        ):
            self.assertIn(list_id, CATALOG)
            self.assertEqual(CATALOG[list_id].role, CatalogRole.DROPOUT)
            self.assertNotIn(list_id, SIGNUP_FUNNEL.list_ids())

    def test_eligible_stage_is_stage_role(self):
        entry = CATALOG["funnel__eligible_for_onboarding"]
        self.assertEqual(entry.role, CatalogRole.STAGE)

    def test_display_meta_reads_labels_from_catalog(self):
        meta = SIGNUP_FUNNEL.display_meta(ALL_CATALOG)
        self.assertEqual(meta["funnel__active_adjusted"]["label"], "Adjusted registered users")
        self.assertEqual(meta["funnel__form_completed"]["label"], "Form completed")
        self.assertEqual(meta["funnel__eligible_for_onboarding"]["label"], "Eligible for onboarding")
        self.assertEqual(meta["funnel__onboarded"]["label"], "Onboarded")

    def test_funnel_steps_have_no_label_overrides(self):
        for step in SIGNUP_FUNNEL.steps:
            self.assertIsNone(step.label_override)
            self.assertIsNone(step.description_override)

    def test_display_meta_applies_overrides_and_merge_groups(self):
        """The override and merge-group branches have no producer yet — cover them here."""
        funnel = FunnelDefinition(
            id="test",
            title="Test",
            mode=FunnelMode.STAGE,
            base_model=User,
            steps=(
                FunnelStep(list_id="funnel__all"),
                FunnelStep(
                    list_id="funnel__onboarded",
                    label_override="Done",
                    description_override="Chart-specific wording",
                ),
            ),
            merge_groups=(
                FunnelMergeGroup(
                    list_ids=("funnel__onboarding_started", "funnel__onboarded"),
                    merge_key="merged__onboarding",
                    display_label="Onboarding",
                    description="Started or finished",
                ),
            ),
        )
        meta = funnel.display_meta(ALL_CATALOG)
        self.assertEqual(meta["funnel__all"]["label"], "Total registered users")
        self.assertEqual(meta["funnel__onboarded"]["label"], "Done")
        self.assertEqual(meta["funnel__onboarded"]["description"], "Chart-specific wording")
        self.assertEqual(meta["merged__onboarding"]["label"], "Onboarding")
        self.assertEqual(meta["merged__onboarding"]["description"], "Started or finished")


class DisplayTimeTests(SimpleTestCase):
    """Date-only bounds are Berlin days, not project-default days (conventions §10)."""

    def test_date_only_bounds_are_berlin_midnight_to_midnight(self):
        start, end = inclusive_range("2026-01-15", "2026-01-15")
        self.assertEqual(start, datetime(2026, 1, 15, 0, 0, 0, 0, tzinfo=DISPLAY_TIMEZONE))
        self.assertEqual(end, datetime(2026, 1, 15, 23, 59, 59, 999999, tzinfo=DISPLAY_TIMEZONE))

    def test_end_of_day_is_inclusive(self):
        self.assertEqual(end_of_day_inclusive(date(2026, 1, 15)).time(), time.max)

    def test_start_of_day_is_midnight(self):
        self.assertEqual(start_of_day(date(2026, 1, 15)).time(), time.min)

    def test_naive_datetime_bound_is_coerced_to_display_timezone(self):
        """Passing it through would make a string and a datetime bound different instants."""
        coerced = parse_end_bound(datetime(2026, 1, 15, 12, 0))  # noqa: DTZ001 — naive is the point
        self.assertEqual(coerced.utcoffset(), timedelta(hours=1))
        self.assertEqual(coerced, datetime(2026, 1, 15, 12, 0, tzinfo=DISPLAY_TIMEZONE))

    def test_aware_datetime_bound_is_preserved(self):
        aware = datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(parse_end_bound(aware), aware)

    def test_date_and_datetime_string_bounds_agree_on_the_day(self):
        from_string = parse_end_bound("2026-06-15")
        from_date = parse_end_bound(date(2026, 6, 15))
        self.assertEqual(from_string, from_date)

    def test_summer_bound_uses_cest(self):
        self.assertEqual(parse_end_bound("2026-06-15").utcoffset(), timedelta(hours=2))

    def test_today_is_the_berlin_calendar_date(self):
        self.assertEqual(today(), datetime.now(DISPLAY_TIMEZONE).date())


class SignupCohortBoundaryTests(TestCase):
    """The Berlin pinning changes which users land in a cohort — assert deliberately."""

    def _user(self, email, joined_at):
        user = User.objects.create(username=email, email=email)
        User.objects.filter(pk=user.pk).update(date_joined=joined_at)
        return user

    def test_end_of_day_boundary_is_berlin_not_utc(self):
        # 23:30 on 15 Jan in Berlin is 22:30 UTC — inside the Berlin day, outside a
        # naive-UTC day only if the bound were misinterpreted.
        inside = self._user("inside@example.com", datetime(2026, 1, 15, 23, 30, tzinfo=DISPLAY_TIMEZONE))
        outside = self._user("outside@example.com", datetime(2026, 1, 16, 0, 15, tzinfo=DISPLAY_TIMEZONE))

        in_cohort = apply_cohort(
            User.objects.all(),
            SignupCohort(start_date="2026-01-15", end_date="2026-01-15"),
        )
        ids = set(in_cohort.values_list("id", flat=True))

        self.assertIn(inside.id, ids)
        self.assertNotIn(outside.id, ids)

    def test_start_of_day_boundary_is_inclusive(self):
        at_midnight = self._user("midnight@example.com", datetime(2026, 1, 15, 0, 0, tzinfo=DISPLAY_TIMEZONE))
        before = self._user("before@example.com", datetime(2026, 1, 14, 23, 59, tzinfo=DISPLAY_TIMEZONE))

        ids = set(
            apply_cohort(
                User.objects.all(),
                SignupCohort(start_date="2026-01-15", end_date="2026-01-15"),
            ).values_list("id", flat=True)
        )

        self.assertIn(at_midnight.id, ids)
        self.assertNotIn(before.id, ids)

    def test_cohort_declares_its_entity(self):
        self.assertIs(SignupCohort(start_date="2026-01-01", end_date="2026-01-02").base_model, User)
