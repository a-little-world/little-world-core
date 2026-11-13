"""Catalog for the user-journey domain.

The catalog owns every label and description (conventions §4). Nothing in the admin
panel should carry a title or description for these IDs.

Two ID namespaces, one domain (conventions §3). Both lead with the *construct*, not a
product phase, so funnel and partition cannot be confused for each other:

``funnel__``
    Cumulative stage reach, plus the shared cohort baseline. Consumed by the signup
    funnel chart.
``state__``
    Mutually exclusive current state. Cells of the user-journey partition.

The split is deliberate and load-bearing. ``funnel__email_verified`` counts every user
who ever verified their email; ``state__form_unfilled`` counts those who verified and
got no further. Reading one as the other is the easiest mistake to make with these
numbers, so the IDs are kept visibly different.
"""

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.roles import CatalogRole
from management.analytics.user_journey.queries import funnel as f
from management.analytics.user_journey.queries import state as s
from management.models.user import User

# A domain may own more than one ID namespace; every namespace it owns is listed here
# and the registry checks both that keys match one of them and that no other domain
# claims the same prefix.
DOMAIN_PREFIXES = ("funnel__", "state__")

_USER = User

# The baseline both constructs count against. One ID, shared — two IDs for one set is
# the drift this domain merge exists to remove.
BASELINE_LIST_ID = "funnel__all"

CATALOG: dict[str, CatalogEntry] = {
    # =======================================================================
    # funnel__ — cumulative stage reach
    # =======================================================================
    "funnel__all": CatalogEntry(
        list_id="funnel__all",
        role=CatalogRole.BASELINE,
        queryset=f.users_all,
        description="All users in the pre-filtered cohort (ordered by date joined).",
        display_name="Total registered users",
        base_model=_USER,
    ),
    "funnel__active_adjusted": CatalogEntry(
        list_id="funnel__active_adjusted",
        role=CatalogRole.STAGE,
        queryset=f.users_active_adjusted,
        description="Active accounts that are not deleted (may still be unverified).",
        display_name="Adjusted registered users",
        base_model=_USER,
    ),
    "funnel__email_verified": CatalogEntry(
        list_id="funnel__email_verified",
        role=CatalogRole.STAGE,
        queryset=f.users_who_verified_email,
        description="Active, non-deleted users who verified their email.",
        display_name="Email verified",
        base_model=_USER,
    ),
    "funnel__form_completed": CatalogEntry(
        list_id="funnel__form_completed",
        role=CatalogRole.STAGE,
        queryset=f.users_who_completed_form,
        description="Users who completed the registration form (includes A0 / outside-DE).",
        display_name="Form completed",
        base_model=_USER,
    ),
    "funnel__eligible_for_onboarding": CatalogEntry(
        list_id="funnel__eligible_for_onboarding",
        role=CatalogRole.STAGE,
        queryset=f.users_eligible_for_onboarding,
        description="Form-complete users not blocked by an active ineligibility reason.",
        display_name="Eligible for onboarding",
        base_model=_USER,
    ),
    "funnel__onboarding_started": CatalogEntry(
        list_id="funnel__onboarding_started",
        role=CatalogRole.STAGE,
        queryset=f.users_who_started_onboarding,
        description="Users who booked a call, started self-onboarding (includes already onboarded).",
        display_name="Onboarding started",
        base_model=_USER,
    ),
    "funnel__onboarded": CatalogEntry(
        list_id="funnel__onboarded",
        role=CatalogRole.STAGE,
        queryset=f.users_who_are_onboarded,
        description="Users who completed onboarding.",
        display_name="Onboarded",
        base_model=_USER,
    ),
    # --- Ineligibility reason subsets (drill-down; not funnel steps) ---
    "funnel__ineligible_a0_german": CatalogEntry(
        list_id="funnel__ineligible_a0_german",
        role=CatalogRole.DROPOUT,
        queryset=f.learners_ineligible_for_onboarding_due_to_a0_german,
        description="Form-complete learners ineligible due to A0 German (force_match_eligible=False).",
        display_name="Ineligible - A0 German",
        base_model=_USER,
    ),
    "funnel__ineligible_outside_germany": CatalogEntry(
        list_id="funnel__ineligible_outside_germany",
        role=CatalogRole.DROPOUT,
        queryset=f.learners_ineligible_for_onboarding_due_to_residence_outside_germany,
        description=(
            "Form-complete learners ineligible due to residence outside Germany (force_match_eligible=False)."
        ),
        display_name="Ineligible - outside Germany",
        base_model=_USER,
    ),
    "funnel__ineligible_for_onboarding": CatalogEntry(
        list_id="funnel__ineligible_for_onboarding",
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
    "funnel__form_completed_awaiting_onboarding": CatalogEntry(
        list_id="funnel__form_completed_awaiting_onboarding",
        role=CatalogRole.STAGE,
        queryset=f.users_with_form_complete_awaiting_onboarding,
        description="Form completed, awaiting onboarding - all users including A0 (stuck bucket).",
        display_name="Form completed (awaiting onboarding)",
        base_model=_USER,
    ),
    # =======================================================================
    # state__ — mutually exclusive current state (partition cells)
    # =======================================================================
    # --- Phase: signup ---
    "state__email_unverified": CatalogEntry(
        list_id="state__email_unverified",
        role=CatalogRole.STAGE,
        queryset=s.signup_created,
        description="Registered but has not verified their email address yet.",
        display_name="Email not verified",
        base_model=_USER,
    ),
    "state__form_unfilled": CatalogEntry(
        list_id="state__form_unfilled",
        role=CatalogRole.STAGE,
        queryset=s.signup_email_verified,
        description="Verified their email address; the registration form is still unfilled.",
        display_name="Form not filled",
        base_model=_USER,
    ),
    "state__onboarding_not_started": CatalogEntry(
        list_id="state__onboarding_not_started",
        role=CatalogRole.STAGE,
        queryset=s.signup_form_completed,
        description="Form complete and eligible to be onboarded, but onboarding has not been started.",
        display_name="Onboarding not started",
        base_model=_USER,
    ),
    "state__onboarding_booked": CatalogEntry(
        list_id="state__onboarding_booked",
        role=CatalogRole.STAGE,
        queryset=s.signup_onboarding_booked,
        description="Form complete with an onboarding call booked in the future.",
        display_name="Onboarding call booked",
        base_model=_USER,
    ),
    "state__self_onboarding": CatalogEntry(
        list_id="state__self_onboarding",
        role=CatalogRole.STAGE,
        queryset=s.signup_self_onboarding,
        description="Started self-onboarding without booking a call, and has not finished it.",
        display_name="Self-onboarding in progress",
        base_model=_USER,
    ),
    "state__onboarding_no_show": CatalogEntry(
        list_id="state__onboarding_no_show",
        role=CatalogRole.DROPOUT,
        queryset=s.signup_no_show,
        description="Booked an onboarding call, did not attend, and has not rebooked.",
        display_name="Onboarding no-show",
        base_model=_USER,
    ),
    "state__onboarding_ineligible": CatalogEntry(
        list_id="state__onboarding_ineligible",
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
    "state__first_search": CatalogEntry(
        list_id="state__first_search",
        role=CatalogRole.COMPOSITE,
        queryset=s.active_first_search,
        description=(
            "Onboarded and searching for a first match, with nothing currently in flight. "
            "A Standard or Random Call match graduates the user out of this group; a "
            "TEMPORARY lobby pairing does not. Rollup of the five cells below, which split "
            "this group by what happened to the user's most recent Standard proposal."
        ),
        display_name="Pre first match - Searching for a first match",
        base_model=_USER,
        members=(
            "state__first_search_no_proposal",
            "state__first_search_proposal_expired",
            "state__first_search_rejected_by_them",
            "state__first_search_rejected_by_partner",
            "state__first_search_proposal_closed",
        ),
    ),
    "state__first_search_no_proposal": CatalogEntry(
        list_id="state__first_search_no_proposal",
        role=CatalogRole.STAGE,
        queryset=s.active_first_search_no_proposal,
        description="Searching for a first match, and nobody has ever been proposed to them.",
        display_name="Pre first match - Searching - never proposed anyone",
        base_model=_USER,
    ),
    "state__first_search_proposal_expired": CatalogEntry(
        list_id="state__first_search_proposal_expired",
        role=CatalogRole.STAGE,
        queryset=s.active_first_search_proposal_expired,
        description="Searching again because their most recent proposal expired undecided.",
        display_name="Pre first match - Searching - last proposal expired",
        base_model=_USER,
    ),
    "state__first_search_rejected_by_them": CatalogEntry(
        list_id="state__first_search_rejected_by_them",
        role=CatalogRole.STAGE,
        queryset=s.active_first_search_rejected_by_them,
        description=(
            "Searching again after turning down their most recent proposal. Only the user who "
            "confirms a proposal can reject it, so this group is mostly learners."
        ),
        display_name="Pre first match - Searching - rejected the last proposal",
        base_model=_USER,
    ),
    "state__first_search_rejected_by_partner": CatalogEntry(
        list_id="state__first_search_rejected_by_partner",
        role=CatalogRole.STAGE,
        queryset=s.active_first_search_rejected_by_partner,
        description=(
            "Searching again after the person proposed to them turned them down. Mostly "
            "volunteers, since the learner is the one who confirms a standard match."
        ),
        display_name="Pre first match - Searching - partner rejected them",
        base_model=_USER,
    ),
    "state__first_search_proposal_closed": CatalogEntry(
        list_id="state__first_search_proposal_closed",
        role=CatalogRole.STAGE,
        queryset=s.active_first_search_proposal_closed,
        description=(
            "Searching again after their most recent proposal was closed without a decision - "
            "withdrawn, superseded, or closed by staff, rather than rejected or expired."
        ),
        display_name="Pre first match - Searching - last proposal closed",
        base_model=_USER,
    ),
    "state__search_blocked": CatalogEntry(
        list_id="state__search_blocked",
        role=CatalogRole.DROPOUT,
        queryset=s.active_search_blocked,
        description=(
            "Onboarded and searching for a first match, but cannot be matched because of A0 "
            "German level or residence outside Germany."
        ),
        display_name="Pre first match - Searching but not matchable",
        base_model=_USER,
    ),
    "state__proposed": CatalogEntry(
        list_id="state__proposed",
        role=CatalogRole.STAGE,
        queryset=s.proposed_never_matched,
        description="Has an open match proposal and has never had a real match.",
        display_name="Pre first match - Open proposal",
        base_model=_USER,
    ),
    "state__gave_up": CatalogEntry(
        list_id="state__gave_up",
        role=CatalogRole.DROPOUT,
        queryset=s.lapsed_gave_up,
        description="Stopped searching without ever being matched.",
        display_name="Pre first match - Stopped searching",
        base_model=_USER,
    ),
    # --- First match in flight (never yet succeeded) ---
    "state__first_match_kickoff": CatalogEntry(
        list_id="state__first_match_kickoff",
        role=CatalogRole.STAGE,
        queryset=s.first_match_kickoff,
        description=(
            "In a match that has not reached sustained two-way contact yet, and has never completed a successful match."
        ),
        display_name="In match - kickoff (Pre-first success)",
        base_model=_USER,
    ),
    "state__first_match_ongoing": CatalogEntry(
        list_id="state__first_match_ongoing",
        role=CatalogRole.STAGE,
        queryset=s.first_match_ongoing,
        description=(
            "In a match with sustained contact that is not yet completed, and has never completed a successful match."
        ),
        display_name="In match - ongoing (Pre-first success)",
        base_model=_USER,
    ),
    # --- After failed first match(es) ---
    "state__rematch_proposed": CatalogEntry(
        list_id="state__rematch_proposed",
        role=CatalogRole.STAGE,
        queryset=s.rematch_proposed,
        description=(
            "Has an open rematch proposal after one or more matches that did not succeed; nothing currently live."
        ),
        display_name="Open proposal - after failed first match(es)",
        base_model=_USER,
    ),
    "state__searching_after_failed": CatalogEntry(
        list_id="state__searching_after_failed",
        role=CatalogRole.STAGE,
        queryset=s.searching_after_failed,
        description=("Back in the matching pool after failed first match(es); no open proposal and nothing live."),
        display_name="Searching again - after failed first match(es)",
        base_model=_USER,
    ),
    "state__stopped_after_failed": CatalogEntry(
        list_id="state__stopped_after_failed",
        role=CatalogRole.DROPOUT,
        queryset=s.stopped_after_failed,
        description="Stopped searching after failed first match(es); nothing in flight.",
        display_name="Stopped searching - after failed first match(es)",
        base_model=_USER,
    ),
    # --- Successful first match (absorbing) ---
    "state__success_ongoing_searching": CatalogEntry(
        list_id="state__success_ongoing_searching",
        role=CatalogRole.STAGE,
        queryset=s.success_ongoing_searching,
        description=(
            "Has completed a successful match and currently has a live match "
            "(not necessarily the successful one); searching again."
        ),
        display_name="Live match(es) & searching (after success)",
        base_model=_USER,
    ),
    "state__success_ongoing_settled": CatalogEntry(
        list_id="state__success_ongoing_settled",
        role=CatalogRole.STAGE,
        queryset=s.success_ongoing_settled,
        description=(
            "Has completed a successful match and currently has a live match "
            "(not necessarily the successful one); not searching."
        ),
        display_name="Live match(es) & not searching (after success)",
        base_model=_USER,
    ),
    "state__success_searching": CatalogEntry(
        list_id="state__success_searching",
        role=CatalogRole.STAGE,
        queryset=s.success_searching,
        description=("Has completed a successful first match, has no live match, and is searching again."),
        display_name="Successful dormant match(es) & searching",
        base_model=_USER,
    ),
    "state__success_idle": CatalogEntry(
        list_id="state__success_idle",
        role=CatalogRole.STAGE,
        queryset=s.success_idle,
        description=("Has completed a successful first match, has no live match, and is not searching."),
        display_name="Successful dormant match(es) & not searching",
        base_model=_USER,
    ),
    # --- Phase: past ---
    "state__unresponsive_after_success": CatalogEntry(
        list_id="state__unresponsive_after_success",
        role=CatalogRole.DROPOUT,
        queryset=s.past_unresponsive_after_success,
        description="Marked unresponsive after completing a successful first match.",
        display_name="Marked unresponsive - successful",
        base_model=_USER,
    ),
    "state__unresponsive": CatalogEntry(
        list_id="state__unresponsive",
        role=CatalogRole.DROPOUT,
        queryset=s.past_unresponsive,
        description="Marked unresponsive without a successful first match.",
        display_name="Marked unresponsive - unsuccessful",
        base_model=_USER,
    ),
    "state__deleted_after_success": CatalogEntry(
        list_id="state__deleted_after_success",
        role=CatalogRole.DROPOUT,
        queryset=s.past_deleted_after_success,
        description="Deleted account after completing a successful first match.",
        display_name="Deleted account - successful",
        base_model=_USER,
    ),
    "state__deleted": CatalogEntry(
        list_id="state__deleted",
        role=CatalogRole.DROPOUT,
        queryset=s.past_deleted,
        description="Deleted account without a successful first match.",
        display_name="Deleted account - unsuccessful",
        base_model=_USER,
    ),
    "state__record_incomplete": CatalogEntry(
        list_id="state__record_incomplete",
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
    "state__failed_match_reasons": CatalogEntry(
        list_id="state__failed_match_reasons",
        role=CatalogRole.DROPOUT,
        queryset=s.lapsed_failed_match_reasons,
        description=(
            "Onboarded users with at least one match in a recorded failure state (never confirmed, "
            "no contact, ghosted, contact stopped, reported or removed). Cuts across the partition - "
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
