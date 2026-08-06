"""Catalog for the user-journey domain.

The catalog owns every label and description (conventions §4). Nothing in the admin
panel should carry a title or description for these IDs.

Two ID namespaces, one domain (conventions §3):

``signup__``
    Cumulative stage reach, plus the shared cohort baseline. Consumed by the signup
    funnel chart and already live in the admin panel, so these IDs are a settled
    contract.
``current__``
    Mutually exclusive current state. Cells of the user-journey partition.

The split is deliberate and load-bearing. ``signup__stage_email_verified`` counts every
user who ever verified their email; ``current__signup_email_verified`` counts only those
who verified and got no further. Reading one as the other is the easiest mistake to make
with these numbers, so the IDs are kept visibly different.
"""

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.roles import CatalogRole
from management.analytics.user_journey.queries import funnel as f
from management.analytics.user_journey.queries import state as s
from management.models.user import User

# A domain may own more than one ID namespace; every namespace it owns is listed here
# and the registry checks both that keys match one of them and that no other domain
# claims the same prefix.
DOMAIN_PREFIXES = ("signup__", "current__")

_USER = User

# The baseline both constructs count against. `signup__all` rather than a second
# `current__all`: the queries were identical (`all_users` only adds an ordering), and two
# IDs for one set is the drift this domain merge exists to remove.
BASELINE_LIST_ID = "signup__all"

CATALOG: dict[str, CatalogEntry] = {
    # =======================================================================
    # signup__ — cumulative stage reach
    # =======================================================================
    "signup__all": CatalogEntry(
        list_id="signup__all",
        role=CatalogRole.BASELINE,
        queryset=f.users_all,
        description="All users in the pre-filtered cohort (ordered by date joined).",
        display_name="Total registered users",
        base_model=_USER,
    ),
    "signup__stage_active_adjusted": CatalogEntry(
        list_id="signup__stage_active_adjusted",
        role=CatalogRole.STAGE,
        queryset=f.users_active_adjusted,
        description="Active accounts that are not deleted (may still be unverified).",
        display_name="Adjusted registered users",
        base_model=_USER,
    ),
    "signup__stage_email_verified": CatalogEntry(
        list_id="signup__stage_email_verified",
        role=CatalogRole.STAGE,
        queryset=f.users_who_verified_email,
        description="Active, non-deleted users who verified their email.",
        display_name="Email verified",
        base_model=_USER,
    ),
    "signup__stage_form_completed": CatalogEntry(
        list_id="signup__stage_form_completed",
        role=CatalogRole.STAGE,
        queryset=f.users_who_completed_form,
        description="Users who completed the registration form (includes A0 / outside-DE).",
        display_name="Form completed",
        base_model=_USER,
    ),
    "signup__stage_eligible_for_onboarding": CatalogEntry(
        list_id="signup__stage_eligible_for_onboarding",
        role=CatalogRole.STAGE,
        queryset=f.users_eligible_for_onboarding,
        description="Form-complete users not blocked by an active ineligibility reason.",
        display_name="Eligible for onboarding",
        base_model=_USER,
    ),
    "signup__stage_onboarding_started": CatalogEntry(
        list_id="signup__stage_onboarding_started",
        role=CatalogRole.STAGE,
        queryset=f.users_who_started_onboarding,
        description="Users who booked a call, started self-onboarding (includes already onboarded).",
        display_name="Onboarding started",
        base_model=_USER,
    ),
    "signup__stage_onboarded": CatalogEntry(
        list_id="signup__stage_onboarded",
        role=CatalogRole.STAGE,
        queryset=f.users_who_are_onboarded,
        description="Users who completed onboarding.",
        display_name="Onboarded",
        base_model=_USER,
    ),
    # --- Ineligibility reason subsets (drill-down; not funnel steps) ---
    "signup__ineligible_a0_german": CatalogEntry(
        list_id="signup__ineligible_a0_german",
        role=CatalogRole.DROPOUT,
        queryset=f.learners_ineligible_for_onboarding_due_to_a0_german,
        description="Form-complete learners ineligible due to A0 German (force_match_eligible=False).",
        display_name="Ineligible — A0 German",
        base_model=_USER,
    ),
    "signup__ineligible_outside_germany": CatalogEntry(
        list_id="signup__ineligible_outside_germany",
        role=CatalogRole.DROPOUT,
        queryset=f.learners_ineligible_for_onboarding_due_to_residence_outside_germany,
        description=(
            "Form-complete learners ineligible due to residence outside Germany (force_match_eligible=False)."
        ),
        display_name="Ineligible — outside Germany",
        base_model=_USER,
    ),
    "signup__ineligible_for_onboarding": CatalogEntry(
        list_id="signup__ineligible_for_onboarding",
        role=CatalogRole.DROPOUT,
        queryset=f.learners_ineligible_for_onboarding,
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
        queryset=f.users_with_form_complete_awaiting_onboarding,
        description="Form completed, awaiting onboarding — all users including A0 (stuck bucket).",
        display_name="Form completed (awaiting onboarding)",
        base_model=_USER,
    ),
    # =======================================================================
    # current__ — mutually exclusive current state (partition cells)
    # =======================================================================
    # --- Phase: signup ---
    "current__signup_created": CatalogEntry(
        list_id="current__signup_created",
        role=CatalogRole.STAGE,
        queryset=s.signup_created,
        description="Registered but has not verified their email address yet.",
        display_name="Email not verified",
        base_model=_USER,
    ),
    "current__signup_email_verified": CatalogEntry(
        list_id="current__signup_email_verified",
        role=CatalogRole.STAGE,
        queryset=s.signup_email_verified,
        description="Verified their email address; the registration form is still unfilled.",
        display_name="Form not filled",
        base_model=_USER,
    ),
    "current__signup_form_completed": CatalogEntry(
        list_id="current__signup_form_completed",
        role=CatalogRole.STAGE,
        queryset=s.signup_form_completed,
        description="Form complete and eligible to be onboarded, but onboarding has not been started.",
        display_name="Onboarding not started",
        base_model=_USER,
    ),
    "current__signup_onboarding_booked": CatalogEntry(
        list_id="current__signup_onboarding_booked",
        role=CatalogRole.STAGE,
        queryset=s.signup_onboarding_booked,
        description="Form complete with an onboarding call booked in the future.",
        display_name="Onboarding call booked",
        base_model=_USER,
    ),
    "current__signup_self_onboarding": CatalogEntry(
        list_id="current__signup_self_onboarding",
        role=CatalogRole.STAGE,
        queryset=s.signup_self_onboarding,
        description="Started self-onboarding without booking a call, and has not finished it.",
        display_name="Self-onboarding in progress",
        base_model=_USER,
    ),
    "current__signup_no_show": CatalogEntry(
        list_id="current__signup_no_show",
        role=CatalogRole.DROPOUT,
        queryset=s.signup_no_show,
        description="Booked an onboarding call, did not attend, and has not rebooked.",
        display_name="Onboarding no-show",
        base_model=_USER,
    ),
    "current__signup_ineligible": CatalogEntry(
        list_id="current__signup_ineligible",
        role=CatalogRole.DROPOUT,
        queryset=s.signup_ineligible,
        description=(
            "Form complete but blocked from onboarding by A0 German level or residence outside "
            "Germany, unless marked force-match-eligible."
        ),
        display_name="Not eligible for onboarding",
        base_model=_USER,
    ),
    # --- Phase: active ---
    "current__active_first_search": CatalogEntry(
        list_id="current__active_first_search",
        role=CatalogRole.STAGE,
        queryset=s.active_first_search,
        description="Onboarded and searching for a first match, signed up within the last 30 days.",
        display_name="Searching for a first match",
        base_model=_USER,
    ),
    "current__active_search_blocked": CatalogEntry(
        list_id="current__active_search_blocked",
        role=CatalogRole.DROPOUT,
        queryset=s.active_search_blocked,
        description=(
            "Onboarded and searching, but cannot be matched because of A0 German level or residence outside Germany."
        ),
        display_name="Searching but not matchable",
        base_model=_USER,
    ),
    "current__active_proposed": CatalogEntry(
        list_id="current__active_proposed",
        role=CatalogRole.STAGE,
        queryset=s.active_proposed,
        description="Has an open match proposal awaiting a decision, and no match of their own yet.",
        display_name="Match proposed",
        base_model=_USER,
    ),
    "current__active_match_takeoff": CatalogEntry(
        list_id="current__active_match_takeoff",
        role=CatalogRole.STAGE,
        queryset=s.active_match_takeoff,
        description="In a match that has not reached sustained two-way contact yet.",
        display_name="Match taking off",
        base_model=_USER,
    ),
    "current__active_match_ongoing": CatalogEntry(
        list_id="current__active_match_ongoing",
        role=CatalogRole.STAGE,
        queryset=s.active_match_ongoing,
        description="In a match with sustained two-way messaging or video calls.",
        display_name="Match ongoing",
        base_model=_USER,
    ),
    "current__active_searching_again": CatalogEntry(
        list_id="current__active_searching_again",
        role=CatalogRole.STAGE,
        queryset=s.active_searching_again,
        description="Back in the matching pool after an earlier match, with nothing currently in flight.",
        display_name="Searching again",
        base_model=_USER,
    ),
    # --- Phase: success ---
    "current__success_match_completed": CatalogEntry(
        list_id="current__success_match_completed",
        role=CatalogRole.STAGE,
        queryset=s.success_match_completed,
        description="Completed a match and is not continuing one past the target duration.",
        display_name="Match completed",
        base_model=_USER,
    ),
    "current__success_free_play": CatalogEntry(
        list_id="current__success_free_play",
        role=CatalogRole.STAGE,
        queryset=s.success_free_play,
        description="Still in regular contact with a match past the target match duration.",
        display_name="Still in contact past target duration",
        base_model=_USER,
    ),
    # --- Phase: lapsed ---
    "current__lapsed_unmatched": CatalogEntry(
        list_id="current__lapsed_unmatched",
        role=CatalogRole.DROPOUT,
        queryset=s.lapsed_unmatched,
        description="Eligible and still searching for a first match more than 30 days after signing up.",
        display_name="Never matched",
        base_model=_USER,
    ),
    "current__lapsed_failed_matching": CatalogEntry(
        list_id="current__lapsed_failed_matching",
        role=CatalogRole.DROPOUT,
        queryset=s.lapsed_failed_matching,
        description="Stopped searching after one or more matches, none of which worked out.",
        display_name="Stopped after a failed match",
        base_model=_USER,
    ),
    "current__lapsed_gave_up": CatalogEntry(
        list_id="current__lapsed_gave_up",
        role=CatalogRole.DROPOUT,
        queryset=s.lapsed_gave_up,
        description="Stopped searching without ever being matched.",
        display_name="Stopped searching",
        base_model=_USER,
    ),
    # --- Phase: past ---
    "current__past_unresponsive": CatalogEntry(
        list_id="current__past_unresponsive",
        role=CatalogRole.DROPOUT,
        queryset=s.past_unresponsive,
        description="Still registered but flagged unresponsive, so excluded from matching.",
        display_name="Marked unresponsive",
        base_model=_USER,
    ),
    "current__past_deleted_after_success": CatalogEntry(
        list_id="current__past_deleted_after_success",
        role=CatalogRole.DROPOUT,
        queryset=s.past_deleted_after_success,
        description="Left the platform having completed a match or continued one past the target duration.",
        display_name="Left after a successful match",
        base_model=_USER,
    ),
    "current__past_deleted": CatalogEntry(
        list_id="current__past_deleted",
        role=CatalogRole.DROPOUT,
        queryset=s.past_deleted,
        description="Left the platform without completing a match.",
        display_name="Left the platform",
        base_model=_USER,
    ),
    "current__record_incomplete": CatalogEntry(
        list_id="current__record_incomplete",
        role=CatalogRole.DROPOUT,
        queryset=s.record_incomplete,
        description=(
            "Still registered but has no state record, so no journey state can be read. "
            "A non-zero count here means account data is missing, not that users are stuck."
        ),
        display_name="Incomplete account record",
        base_model=_USER,
    ),
    # --- Drill-down (not a partition cell) ---
    "current__failed_match_reasons": CatalogEntry(
        list_id="current__failed_match_reasons",
        role=CatalogRole.DROPOUT,
        queryset=s.lapsed_failed_match_reasons,
        description=(
            "Onboarded users with at least one match in a recorded failure state (never confirmed, "
            "no contact, ghosted, contact stopped, reported or removed). Cuts across the partition — "
            "a user can hold both a failed and a live match."
        ),
        display_name="Has a failed match",
        base_model=_USER,
    ),
}


def _assert_catalog_prefixes() -> None:
    for key in CATALOG:
        if not key.startswith(DOMAIN_PREFIXES):
            raise ValueError(f"Catalog key {key!r} must start with one of {DOMAIN_PREFIXES!r}")


_assert_catalog_prefixes()
