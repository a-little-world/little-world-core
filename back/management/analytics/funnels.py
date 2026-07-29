"""Server-owned signup funnel shape.

This funnel uses **stage semantics**: each bar is the membership count of that
stage (users who reached it). Labels match queries. No arithmetic subtraction.

Ineligibility reason subsets live in the catalog for drill-down / future
composition; they are not funnel steps.
"""

from dataclasses import dataclass
from enum import StrEnum

from management.analytics.catalog import SIGNUP_FUNNEL_CATALOG
from management.analytics.roles import CatalogRole


class FunnelMode(StrEnum):
    STAGE = "stage"  # bar = membership count (nested reaches)
    DROPOUT = "dropout"  # bar = remaining after subtracting membership (legacy)


# Stage funnel: only baseline + stage. Dropouts/segments belong in catalog only.
FUNNEL_ALLOWED_ROLES = frozenset(
    {
        CatalogRole.BASELINE,
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
    mode: FunnelMode
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
    mode=FunnelMode.STAGE,
    steps=(
        FunnelStep(
            list_id="all",
            display_label="Total registered users",
            description="Signup-date cohort baseline (100%). Current-state snapshot.",
        ),
        FunnelStep(
            list_id="signup__stage_active_adjusted",
            display_label="Active registered users",
            description="Active accounts that are not deleted (may still be unverified).",
        ),
        FunnelStep(
            list_id="signup__stage_email_verified",
            display_label="Email verified",
            description="Active, non-deleted users who verified their email.",
        ),
        FunnelStep(
            list_id="signup__stage_form_completed",
            display_label="Form completed",
            description="Users who completed the registration form (includes A0 / outside-DE).",
        ),
        FunnelStep(
            list_id="signup__stage_eligible_for_onboarding",
            display_label="Eligible for onboarding",
            description=(
                "Form-complete users not blocked by an active ineligibility reason "
                "(A0 German or residence outside Germany, unless force_match_eligible=True)."
            ),
        ),
        FunnelStep(
            list_id="signup__stage_onboarding_started",
            display_label="Onboarding started",
            description="Users who booked a call, started self-onboarding, or finished onboarding.",
        ),
        FunnelStep(
            list_id="signup__stage_onboarded",
            display_label="Onboarded",
            description="Users who completed onboarding.",
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
    """Return list_ids whose catalog role is not allowed as a funnel step."""
    bad: list[str] = []
    for list_id in funnel.list_ids():
        entry = SIGNUP_FUNNEL_CATALOG[list_id]
        if entry.role not in FUNNEL_ALLOWED_ROLES:
            bad.append(list_id)
    return bad
