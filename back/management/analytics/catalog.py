from collections.abc import Callable
from dataclasses import dataclass

from django.db.models import QuerySet

from management.analytics import queries as q
from management.analytics.roles import CatalogRole


@dataclass(frozen=True)
class CatalogEntry:
    """Stable list ID → membership query + role.

    ``list_id`` keeps legacy ``journey_v2__*`` / ``all`` keys for API compatibility,
    plus new ``signup__*`` ids for analytics-owned definitions.
    """

    list_id: str
    role: CatalogRole
    queryset: Callable[[QuerySet], QuerySet]
    description: str
    display_name: str


SIGNUP_FUNNEL_CATALOG: dict[str, CatalogEntry] = {
    # --- Baseline ---
    "all": CatalogEntry(
        list_id="all",
        role=CatalogRole.BASELINE,
        queryset=q.users_all,
        description="All users in the pre-filtered cohort (ordered by date joined).",
        display_name="Total registered users",
    ),
    # --- Stage reaches (signup funnel) ---
    "signup__stage_active_adjusted": CatalogEntry(
        list_id="signup__stage_active_adjusted",
        role=CatalogRole.STAGE,
        queryset=q.users_active_adjusted,
        description="Active accounts that are not deleted (may still be unverified).",
        display_name="Adjusted registered users",
    ),
    "signup__stage_email_verified": CatalogEntry(
        list_id="signup__stage_email_verified",
        role=CatalogRole.STAGE,
        queryset=q.users_who_verified_email,
        description="Active, non-deleted users who verified their email.",
        display_name="Email verified",
    ),
    "signup__stage_form_completed": CatalogEntry(
        list_id="signup__stage_form_completed",
        role=CatalogRole.STAGE,
        queryset=q.users_who_completed_form,
        description="Users who completed the registration form (includes A0 / outside-DE).",
        display_name="Form completed",
    ),
    "signup__stage_eligible_for_onboarding": CatalogEntry(
        list_id="signup__stage_eligible_for_onboarding",
        role=CatalogRole.STAGE,
        queryset=q.users_eligible_for_onboarding,
        description="Form-complete users not blocked by an active ineligibility reason.",
        display_name="Eligible for onboarding",
    ),
    "signup__stage_onboarding_started": CatalogEntry(
        list_id="signup__stage_onboarding_started",
        role=CatalogRole.STAGE,
        queryset=q.users_who_started_onboarding,
        description="Users who booked a call, started self-onboarding (includes already onboarded).",
        display_name="Onboarding started",
    ),
    "signup__stage_onboarded": CatalogEntry(
        list_id="signup__stage_onboarded",
        role=CatalogRole.STAGE,
        queryset=q.users_who_are_onboarded,
        description="Users who completed onboarding.",
        display_name="Onboarded",
    ),
    # --- Ineligibility reason subsets (drill-down / future composition; not funnel steps) ---
    "signup__ineligible_a0_german": CatalogEntry(
        list_id="signup__ineligible_a0_german",
        role=CatalogRole.DROPOUT,
        queryset=q.learners_ineligible_for_onboarding_due_to_a0_german,
        description="Form-complete learners ineligible due to A0 German (force_match_eligible=False).",
        display_name="Ineligible — A0 German",
    ),
    "signup__ineligible_outside_germany": CatalogEntry(
        list_id="signup__ineligible_outside_germany",
        role=CatalogRole.DROPOUT,
        queryset=q.learners_ineligible_for_onboarding_due_to_residence_outside_germany,
        description=(
            "Form-complete learners ineligible due to residence outside Germany (force_match_eligible=False)."
        ),
        display_name="Ineligible — outside Germany",
    ),
    "signup__invalid_german_level": CatalogEntry(
        list_id="signup__invalid_german_level",
        role=CatalogRole.DROPOUT,
        queryset=q.learners_ineligible_for_onboarding,
        description=(
            "Union of active onboarding-ineligibility reasons "
            "(A0 German + residence outside Germany). "
            "Used to define the eligible-for-onboarding stage gate."
        ),
        display_name="Ineligible for onboarding",
    ),
    # --- Legacy / stuck buckets (other charts & journey lists) ---
    "journey_v2__never_active_or_deleted": CatalogEntry(
        list_id="journey_v2__never_active_or_deleted",
        role=CatalogRole.DROPOUT,
        queryset=q.users_never_active_or_deleted,
        description="Deactivated, deleted, or signups that never verified email.",
        display_name="Never active or deleted",
    ),
    "journey_v2__email_verified": CatalogEntry(
        list_id="journey_v2__email_verified",
        role=CatalogRole.STAGE,
        queryset=q.users_with_verified_email_form_unfilled,
        description="Email verified; registration form still unfilled (stuck bucket).",
        display_name="Email verified (form incomplete)",
    ),
    "journey_v2__user_form_completed": CatalogEntry(
        list_id="journey_v2__user_form_completed",
        role=CatalogRole.STAGE,
        queryset=q.users_with_form_complete_awaiting_onboarding_excluding_a0_german,
        description="Form completed, awaiting onboarding, excluding A0 German (legacy journey list).",
        display_name="Form completed (excl. A0 German)",
    ),
    "signup__form_completed_awaiting_onboarding": CatalogEntry(
        list_id="signup__form_completed_awaiting_onboarding",
        role=CatalogRole.STAGE,
        queryset=q.users_with_form_complete_awaiting_onboarding,
        description="Form completed, awaiting onboarding — all users including A0 (stuck bucket).",
        display_name="Form completed (awaiting onboarding)",
    ),
    "journey_v2__too_low_german_level": CatalogEntry(
        list_id="journey_v2__too_low_german_level",
        role=CatalogRole.SEGMENT,
        queryset=q.learners_with_german_level_a0,
        description="All learners with German language level A0 (global segment, not a funnel step).",
        display_name="Learners with A0 German",
    ),
    "journey_v2__booked_onboarding_call": CatalogEntry(
        list_id="journey_v2__booked_onboarding_call",
        role=CatalogRole.STAGE,
        queryset=q.users_with_booked_onboarding_call,
        description="Future onboarding / prematching call booked.",
        display_name="Booked onboarding call",
    ),
    "journey_v2__self_onboarding_started": CatalogEntry(
        list_id="journey_v2__self_onboarding_started",
        role=CatalogRole.STAGE,
        queryset=q.users_with_self_onboarding_started,
        description="Self-onboarding started; no future booked call.",
        display_name="Self-onboarding started",
    ),
    "journey_v2__no_show": CatalogEntry(
        list_id="journey_v2__no_show",
        role=CatalogRole.DROPOUT,
        queryset=q.users_who_no_showed_onboarding,
        description="Booked onboarding but did not attend (past appointment, not onboarded).",
        display_name="Onboarding no-show",
    ),
}


def get_catalog_entry(list_id: str) -> CatalogEntry | None:
    return SIGNUP_FUNNEL_CATALOG.get(list_id)
