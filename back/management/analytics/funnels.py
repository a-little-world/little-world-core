"""Server-owned signup funnel shape (display vs subtract).

Chart bars still use dropout-style subtraction on the frontend for now.
``display_label`` is what the bar represents after subtraction — not the
membership query name (e.g. ``no_show`` → \"Onboarded users\").
"""

from dataclasses import dataclass

from management.analytics.catalog import SIGNUP_FUNNEL_CATALOG
from management.analytics.roles import CatalogRole

# Roles allowed as funnel subtract / baseline steps.
# SEGMENT is intentionally excluded — segments belong in CohortSpec only.
FUNNEL_ALLOWED_ROLES = frozenset(
    {
        CatalogRole.BASELINE,
        CatalogRole.DROPOUT,
        CatalogRole.STAGE,
    }
)


@dataclass(frozen=True)
class FunnelMergeGroup:
    list_ids: tuple[str, ...]
    merge_key: str
    display_label: str
    description: str = ""


@dataclass(frozen=True)
class FunnelStep:
    list_id: str
    display_label: str
    description: str = ""


@dataclass(frozen=True)
class SignupFunnelDefinition:
    id: str
    title: str
    steps: tuple[FunnelStep, ...]
    merge_groups: tuple[FunnelMergeGroup, ...] = ()

    def list_ids(self) -> list[str]:
        return [step.list_id for step in self.steps]

    def display_meta(self) -> dict[str, dict[str, str]]:
        """Map list_id (and merge keys) → {label, description?} for the chart."""
        meta: dict[str, dict[str, str]] = {}
        for step in self.steps:
            entry: dict[str, str] = {"label": step.display_label}
            if step.description:
                entry["description"] = step.description
            meta[step.list_id] = entry
        for group in self.merge_groups:
            entry = {"label": group.display_label}
            if group.description:
                entry["description"] = group.description
            meta[group.merge_key] = entry
        return meta


SIGNUP_FUNNEL = SignupFunnelDefinition(
    id="user-signup-funnel",
    title="User Signup Funnel",
    steps=(
        FunnelStep(
            list_id="all",
            display_label="Total registered users",
            description=(
                "Signup-date cohort baseline (100%). "
                "⚠ Snapshot semantics: users classified by current state, not state at signup date. "
                "See migration plan commit 4 for event-based transitions."
            ),
        ),
        FunnelStep(
            list_id="journey_v2__never_active_or_deleted",
            display_label="Registered users (adjusted)",
            description="Remaining after removing deactivated, deleted, and never-verified signups.",
        ),
        FunnelStep(
            list_id="journey_v2__email_verified",
            display_label="Email verified (form incomplete)",
            description="Remaining after removing users stuck at verified-email with form still unfilled.",
        ),
        FunnelStep(
            list_id="journey_v2__user_form_completed",
            display_label="Form completed",
            description=(
                "Remaining after removing users who completed the form but have not yet started "
                "onboarding. Note: this query already excludes A0 German learners (they appear in "
                "the next step instead)."
            ),
        ),
        FunnelStep(
            list_id="signup__invalid_german_level",
            display_label="Language-eligible (B1+ German)",
            description=(
                "Remaining after removing form-complete learners ineligible for onboarding "
                "(A0 German, not onboarded, no appointment). "
                "True partition of form-complete users — not the global A0 segment."
            ),
        ),
        FunnelStep(
            list_id="journey_v2__booked_onboarding_call",
            display_label="Booked call",
            description="Bucket membership: future onboarding call booked (merged into Onboarding started).",
        ),
        FunnelStep(
            list_id="journey_v2__self_onboarding_started",
            display_label="Self-onboarding started",
            description="Bucket membership: self-onboarding started (merged into Onboarding started).",
        ),
        FunnelStep(
            list_id="journey_v2__no_show",
            display_label="Onboarded users",
            description=(
                "Remaining after subtracting no-shows (users with a past appointment who never "
                "onboarded). The membership query is no-shows; the bar shows who is onboarded."
            ),
        ),
    ),
    merge_groups=(
        FunnelMergeGroup(
            list_ids=(
                "journey_v2__booked_onboarding_call",
                "journey_v2__self_onboarding_started",
            ),
            merge_key="Onboarding started",
            display_label="Onboarding started",
            description="Booked call + self-onboarding combined for one funnel step.",
        ),
    ),
)


def assert_funnel_steps_in_catalog(funnel: SignupFunnelDefinition = SIGNUP_FUNNEL) -> None:
    missing = [sid for sid in funnel.list_ids() if sid not in SIGNUP_FUNNEL_CATALOG]
    if missing:
        raise AssertionError(f"Funnel steps missing from catalog: {missing}")


def funnel_steps_with_disallowed_roles(
    funnel: SignupFunnelDefinition = SIGNUP_FUNNEL,
) -> list[str]:
    """Return list_ids whose catalog role is not allowed as a funnel step.

    Segments must never appear here — they belong in CohortSpec only.
    """
    bad: list[str] = []
    for list_id in funnel.list_ids():
        entry = SIGNUP_FUNNEL_CATALOG[list_id]
        if entry.role not in FUNNEL_ALLOWED_ROLES:
            bad.append(list_id)
    return bad
