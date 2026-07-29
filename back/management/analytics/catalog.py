from dataclasses import dataclass
from typing import Callable

from django.db.models import QuerySet

from management.analytics import queries as q
from management.analytics.roles import CatalogRole


@dataclass(frozen=True)
class CatalogEntry:
    """Stable list ID → membership query + role.

    ``list_id`` keeps legacy ``journey_v2__*`` / ``all`` keys for API compatibility.
    """

    list_id: str
    role: CatalogRole
    queryset: Callable[[QuerySet], QuerySet]
    description: str
    display_name: str


SIGNUP_FUNNEL_CATALOG: dict[str, CatalogEntry] = {
    "all": CatalogEntry(
        list_id="all",
        role=CatalogRole.BASELINE,
        queryset=q.users_all,
        description="All users in the pre-filtered cohort (ordered by date joined).",
        display_name="Total registered users",
    ),
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
        description="Email verified; registration form still unfilled.",
        display_name="Email verified (form incomplete)",
    ),
    "journey_v2__user_form_completed": CatalogEntry(
        list_id="journey_v2__user_form_completed",
        role=CatalogRole.STAGE,
        queryset=q.users_with_form_complete_no_onboarding_call,
        description="Form completed; no onboarding call booked yet.",
        display_name="Form completed (no call)",
    ),
    # Segment: global A0 cohort trait — used only for cohort pre-filtering, not as a funnel step.
    "journey_v2__too_low_german_level": CatalogEntry(
        list_id="journey_v2__too_low_german_level",
        role=CatalogRole.SEGMENT,
        queryset=q.learners_with_german_level_a0,
        description="All learners with German language level A0 / below B1 (global segment, not a funnel step).",
        display_name="Learners with A0 German",
    ),
    # Dropout: form-complete learners who cannot proceed to onboarding due to German level.
    # True partition of form-complete users — not the global A0 segment.
    "signup__invalid_german_level": CatalogEntry(
        list_id="signup__invalid_german_level",
        role=CatalogRole.DROPOUT,
        queryset=q.learners_ineligible_for_onboarding,
        description=(
            "Form-complete learners ineligible for onboarding due to German level "
            "(A0, not onboarded, no appointment, force_match_eligible=False)."
        ),
        display_name="Invalid German level for onboarding",
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
