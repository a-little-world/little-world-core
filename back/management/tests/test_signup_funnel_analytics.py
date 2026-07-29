from django.test import SimpleTestCase

from management.analytics.catalog import SIGNUP_FUNNEL_CATALOG
from management.analytics.funnels import (
    FUNNEL_ALLOWED_ROLES,
    SIGNUP_FUNNEL,
    FunnelMode,
    assert_funnel_steps_in_catalog,
    funnel_steps_with_disallowed_roles,
)
from management.analytics.roles import CatalogRole


class SignupFunnelAnalyticsStructureTests(SimpleTestCase):
    def test_every_funnel_step_is_in_catalog(self):
        assert_funnel_steps_in_catalog(SIGNUP_FUNNEL)

    def test_funnel_is_stage_mode(self):
        self.assertEqual(SIGNUP_FUNNEL.mode, FunnelMode.STAGE)

    def test_funnel_list_ids_order(self):
        self.assertEqual(
            SIGNUP_FUNNEL.list_ids(),
            [
                "all",
                "signup__stage_active_adjusted",
                "signup__stage_email_verified",
                "signup__stage_form_completed",
                "signup__stage_eligible_for_onboarding",
                "signup__stage_onboarding_started",
                "signup__stage_onboarded",
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
            "signup__ineligible_a0_german",
            "signup__ineligible_outside_germany",
            "signup__invalid_german_level",
        ):
            self.assertIn(list_id, SIGNUP_FUNNEL_CATALOG)
            self.assertEqual(SIGNUP_FUNNEL_CATALOG[list_id].role, CatalogRole.DROPOUT)
            self.assertNotIn(list_id, SIGNUP_FUNNEL.list_ids())

    def test_eligible_stage_is_stage_role(self):
        entry = SIGNUP_FUNNEL_CATALOG["signup__stage_eligible_for_onboarding"]
        self.assertEqual(entry.role, CatalogRole.STAGE)

    def test_display_meta_matches_stage_labels(self):
        meta = SIGNUP_FUNNEL.display_meta()
        self.assertEqual(meta["signup__stage_form_completed"]["label"], "Form completed")
        self.assertEqual(meta["signup__stage_eligible_for_onboarding"]["label"], "Eligible for onboarding")
        self.assertEqual(meta["signup__stage_onboarded"]["label"], "Onboarded")
