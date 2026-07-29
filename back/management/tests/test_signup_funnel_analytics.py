from django.test import SimpleTestCase

from management.analytics.catalog import SIGNUP_FUNNEL_CATALOG
from management.analytics.funnels import (
    SIGNUP_FUNNEL,
    assert_funnel_steps_in_catalog,
    funnel_steps_with_disallowed_roles,
)
from management.analytics.roles import CatalogRole


class SignupFunnelAnalyticsStructureTests(SimpleTestCase):
    def test_every_funnel_step_is_in_catalog(self):
        assert_funnel_steps_in_catalog(SIGNUP_FUNNEL)

    def test_funnel_list_ids_order(self):
        self.assertEqual(
            SIGNUP_FUNNEL.list_ids(),
            [
                "all",
                "journey_v2__never_active_or_deleted",
                "journey_v2__email_verified",
                "journey_v2__user_form_completed",
                "signup__invalid_german_level",
                "journey_v2__booked_onboarding_call",
                "journey_v2__self_onboarding_started",
                "journey_v2__no_show",
            ],
        )

    def test_german_step_is_dropout_not_segment(self):
        entry = SIGNUP_FUNNEL_CATALOG["signup__invalid_german_level"]
        self.assertEqual(entry.role, CatalogRole.DROPOUT)

    def test_global_german_segment_still_in_catalog_but_not_a_funnel_step(self):
        entry = SIGNUP_FUNNEL_CATALOG["journey_v2__too_low_german_level"]
        self.assertEqual(entry.role, CatalogRole.SEGMENT)
        self.assertNotIn("journey_v2__too_low_german_level", SIGNUP_FUNNEL.list_ids())
        self.assertNotIn("signup__blocked_german_level", SIGNUP_FUNNEL.list_ids())

    def test_no_show_is_dropout(self):
        entry = SIGNUP_FUNNEL_CATALOG["journey_v2__no_show"]
        self.assertEqual(entry.role, CatalogRole.DROPOUT)
        self.assertIn("no-show", entry.description.lower())

    def test_no_segment_steps_in_funnel(self):
        """Segments must not appear as funnel subtract steps."""
        self.assertEqual(funnel_steps_with_disallowed_roles(SIGNUP_FUNNEL), [])

    def test_display_meta_includes_merge_key_and_new_german_step(self):
        meta = SIGNUP_FUNNEL.display_meta()
        self.assertEqual(meta["Onboarding started"]["label"], "Onboarding started")
        self.assertEqual(meta["signup__invalid_german_level"]["label"], "Language-eligible (B1+ German)")
        self.assertEqual(meta["journey_v2__no_show"]["label"], "Onboarded users")
