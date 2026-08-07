"""Partition machinery and the V5 user journey definition.

A partition is not a funnel. ``FunnelDefinition`` steps are cumulative stage reaches —
``funnel__email_verified`` includes everyone who later onboarded — so summing them
is meaningless. A partition's buckets are current-state cells: every member of the
baseline belongs to exactly one, and the counts sum to the total. Mixing the two is what
made the V4 overview report overlaps and missing users it could not explain.

Machinery placement: ``PartitionBucket`` / ``PartitionPhase`` / ``PartitionDefinition`` are
domain-agnostic but live here, because the journey is their only caller today
(conventions §1 — promote on the second caller, not in anticipation). The match journey
overview is also a partition; move these to ``core/partitions.py`` when it migrates.
"""

from dataclasses import dataclass

from django.db.models import Model

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.roles import CatalogRole
from management.models.user import User

# A partition cell is a current state or an exit. A BASELINE is the denominator, not a
# cell, and a SEGMENT is a cohort trait that overlaps every state (conventions §3) —
# `journey_v2__too_low_german_level` was one, and it is why V4 could never balance.
PARTITION_ALLOWED_ROLES = frozenset(
    {
        CatalogRole.STAGE,
        CatalogRole.DROPOUT,
    }
)


@dataclass(frozen=True)
class PartitionBucket:
    list_id: str
    label_override: str | None = None
    description_override: str | None = None


@dataclass(frozen=True)
class PartitionPhase:
    id: str
    title: str
    buckets: tuple[PartitionBucket, ...]


@dataclass(frozen=True)
class PartitionDefinition:
    id: str
    title: str
    description: str
    base_model: type[Model]
    baseline_list_id: str
    phases: tuple[PartitionPhase, ...]

    def bucket_ids(self) -> list[str]:
        return [bucket.list_id for phase in self.phases for bucket in phase.buckets]

    def all_list_ids(self) -> list[str]:
        """Baseline plus every bucket — what a caller must request to check the partition."""
        return [self.baseline_list_id, *self.bucket_ids()]

    def display_meta(self, catalog: dict[str, CatalogEntry]) -> dict[str, dict[str, str]]:
        """Map list_id → {label, description} for every bucket and the baseline.

        Labels resolve from the catalog; overrides exist for genuinely chart-specific
        wording and should be rare enough to notice in review (conventions §4).
        """
        meta: dict[str, dict[str, str]] = {}
        baseline = catalog[self.baseline_list_id]
        meta[self.baseline_list_id] = {
            "label": baseline.display_name,
            "description": baseline.description,
        }
        for phase in self.phases:
            for bucket in phase.buckets:
                entry = catalog[bucket.list_id]
                meta[bucket.list_id] = {
                    "label": bucket.label_override or entry.display_name,
                    "description": bucket.description_override or entry.description,
                }
        return meta

    def rollups(self, catalog: dict[str, CatalogEntry]) -> list[CatalogEntry]:
        """Composite entries whose members are all cells of this partition.

        A rollup is a subtotal over cells the chart already shows — "searching for a first
        match", across the five ways that search can currently look. Deriving it from the
        catalog rather than listing it on the phase keeps the grouping in one place: add a
        sixth cell to the composite's ``members`` and the subtotal follows.
        """
        cells = set(self.bucket_ids())
        return [
            entry
            for entry in catalog.values()
            if entry.role is CatalogRole.COMPOSITE and entry.members and set(entry.members) <= cells
        ]

    def as_payload(self, catalog: dict[str, CatalogEntry]) -> dict:
        """Server-owned shape the admin panel renders directly.

        The client holds no titles, descriptions or bucket ordering for this journey —
        that duplication is what let V4's ``buckets.ts`` drift from the queries, and it
        already carried two different titles for ``journey_v2__pre_matching``.
        """
        meta = self.display_meta(catalog)
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "baseline_list_id": self.baseline_list_id,
            "phases": [
                {
                    "id": phase.id,
                    "title": phase.title,
                    "buckets": [
                        {
                            "list_id": bucket.list_id,
                            "label": meta[bucket.list_id]["label"],
                            "description": meta[bucket.list_id]["description"],
                        }
                        for bucket in phase.buckets
                    ],
                }
                for phase in self.phases
            ],
            "rollups": [
                {
                    "list_id": entry.list_id,
                    "label": entry.display_name,
                    "description": entry.description,
                    "members": list(entry.members),
                }
                for entry in self.rollups(catalog)
            ],
        }


USER_JOURNEY_V5 = PartitionDefinition(
    id="user-journey-v5",
    title="The User Journey V5",
    description=(
        "Current state of every user who signed up in the selected period. Each user is "
        "counted in exactly one bucket, so the buckets sum to the total."
    ),
    base_model=User,
    baseline_list_id="funnel__all",
    phases=(
        PartitionPhase(
            id="signup",
            title="Sign-up",
            buckets=(
                PartitionBucket(list_id="state__email_unverified"),
                PartitionBucket(list_id="state__form_unfilled"),
                PartitionBucket(list_id="state__onboarding_not_started"),
                PartitionBucket(list_id="state__onboarding_booked"),
                PartitionBucket(list_id="state__self_onboarding"),
                PartitionBucket(list_id="state__onboarding_no_show"),
                PartitionBucket(list_id="state__onboarding_ineligible"),
            ),
        ),
        PartitionPhase(
            id="pre_match",
            title="Pre-match",
            buckets=(
                PartitionBucket(list_id="state__gave_up"),
                PartitionBucket(list_id="state__first_search_no_proposal"),
                PartitionBucket(list_id="state__first_search_proposal_expired"),
                PartitionBucket(list_id="state__first_search_rejected_by_them"),
                PartitionBucket(list_id="state__first_search_rejected_by_partner"),
                PartitionBucket(list_id="state__first_search_proposal_closed"),
                PartitionBucket(list_id="state__search_blocked"),
                PartitionBucket(list_id="state__proposed"),
            ),
        ),
        PartitionPhase(
            id="first_match",
            title="First match",
            buckets=(
                PartitionBucket(list_id="state__first_match_kickoff"),
                PartitionBucket(list_id="state__first_match_ongoing"),
            ),
        ),
        PartitionPhase(
            id="after_failed_first",
            title="After failed first match",
            buckets=(
                PartitionBucket(list_id="state__rematch_proposed"),
                PartitionBucket(list_id="state__searching_after_failed"),
                PartitionBucket(list_id="state__stopped_after_failed"),
            ),
        ),
        PartitionPhase(
            id="successful_first",
            title="Successful first match",
            buckets=(
                PartitionBucket(list_id="state__success_ongoing_searching"),
                PartitionBucket(list_id="state__success_ongoing_settled"),
                PartitionBucket(list_id="state__success_searching"),
                PartitionBucket(list_id="state__success_idle"),
            ),
        ),
        PartitionPhase(
            id="past",
            title="Past users",
            buckets=(
                PartitionBucket(list_id="state__unresponsive_after_success"),
                PartitionBucket(list_id="state__unresponsive"),
                PartitionBucket(list_id="state__deleted_after_success"),
                PartitionBucket(list_id="state__deleted"),
                PartitionBucket(list_id="state__record_incomplete"),
            ),
        ),
    ),
)
