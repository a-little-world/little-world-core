from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.roles import CatalogRole
from management.analytics.signup import queries as q
from management.models.user import User

DOMAIN_PREFIX = "signup"
_PREFIX = f"{DOMAIN_PREFIX}__"

_USER = User

CATALOG: dict[str, CatalogEntry] = {
    # --- Baseline ---
    "signup__all": CatalogEntry(
        list_id="signup__all",
        role=CatalogRole.BASELINE,
        queryset=q.users_all,
        description="All users in the pre-filtered cohort (ordered by date joined).",
        display_name="Total registered users",
        base_model=_USER,
    ),
    # --- Stage reaches (signup funnel) ---
    "signup__stage_active_adjusted": CatalogEntry(
        list_id="signup__stage_active_adjusted",
        role=CatalogRole.STAGE,
        queryset=q.users_active_adjusted,
        description="Active accounts that are not deleted (may still be unverified).",
        display_name="Adjusted registered users",
        base_model=_USER,
    ),
    "signup__stage_email_verified": CatalogEntry(
        list_id="signup__stage_email_verified",
        role=CatalogRole.STAGE,
        queryset=q.users_who_verified_email,
        description="Active, non-deleted users who verified their email.",
        display_name="Email verified",
        base_model=_USER,
    ),
    "signup__stage_form_completed": CatalogEntry(
        list_id="signup__stage_form_completed",
        role=CatalogRole.STAGE,
        queryset=q.users_who_completed_form,
        description="Users who completed the registration form (includes A0 / outside-DE).",
        display_name="Form completed",
        base_model=_USER,
    ),
    "signup__stage_eligible_for_onboarding": CatalogEntry(
        list_id="signup__stage_eligible_for_onboarding",
        role=CatalogRole.STAGE,
        queryset=q.users_eligible_for_onboarding,
        description="Form-complete users not blocked by an active ineligibility reason.",
        display_name="Eligible for onboarding",
        base_model=_USER,
    ),
    "signup__stage_onboarding_started": CatalogEntry(
        list_id="signup__stage_onboarding_started",
        role=CatalogRole.STAGE,
        queryset=q.users_who_started_onboarding,
        description="Users who booked a call, started self-onboarding (includes already onboarded).",
        display_name="Onboarding started",
        base_model=_USER,
    ),
    "signup__stage_onboarded": CatalogEntry(
        list_id="signup__stage_onboarded",
        role=CatalogRole.STAGE,
        queryset=q.users_who_are_onboarded,
        description="Users who completed onboarding.",
        display_name="Onboarded",
        base_model=_USER,
    ),
    # --- Ineligibility reason subsets (drill-down / future composition; not funnel steps) ---
    "signup__ineligible_a0_german": CatalogEntry(
        list_id="signup__ineligible_a0_german",
        role=CatalogRole.DROPOUT,
        queryset=q.learners_ineligible_for_onboarding_due_to_a0_german,
        description="Form-complete learners ineligible due to A0 German (force_match_eligible=False).",
        display_name="Ineligible — A0 German",
        base_model=_USER,
    ),
    "signup__ineligible_outside_germany": CatalogEntry(
        list_id="signup__ineligible_outside_germany",
        role=CatalogRole.DROPOUT,
        queryset=q.learners_ineligible_for_onboarding_due_to_residence_outside_germany,
        description=(
            "Form-complete learners ineligible due to residence outside Germany (force_match_eligible=False)."
        ),
        display_name="Ineligible — outside Germany",
        base_model=_USER,
    ),
    "signup__ineligible_for_onboarding": CatalogEntry(
        list_id="signup__ineligible_for_onboarding",
        role=CatalogRole.DROPOUT,
        queryset=q.learners_ineligible_for_onboarding,
        description=(
            "Union of active onboarding-ineligibility reasons "
            "(A0 German + residence outside Germany). "
            "Used to define the eligible-for-onboarding stage gate."
        ),
        display_name="Ineligible for onboarding",
        base_model=_USER,
    ),
    "signup__form_completed_awaiting_onboarding": CatalogEntry(
        list_id="signup__form_completed_awaiting_onboarding",
        role=CatalogRole.STAGE,
        queryset=q.users_with_form_complete_awaiting_onboarding,
        description="Form completed, awaiting onboarding — all users including A0 (stuck bucket).",
        display_name="Form completed (awaiting onboarding)",
        base_model=_USER,
    ),
}


def _assert_catalog_prefixes() -> None:
    for key in CATALOG:
        if not key.startswith(_PREFIX):
            raise ValueError(f"Catalog key {key!r} must start with {_PREFIX!r}")


_assert_catalog_prefixes()
