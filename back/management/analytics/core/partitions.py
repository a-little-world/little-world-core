"""Partition machinery — domain-agnostic (conventions §1, §17).

Promoted from ``user_journey/partitions.py`` when ``match_journey`` became the second
caller. Domains keep their ``PartitionDefinition`` instances; only the types live here.
"""

from dataclasses import dataclass

from django.db.models import Model

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.roles import CatalogRole

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
        """Map list_id → {label, description} for every bucket and the baseline."""
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
        """Composite entries whose members are all cells of this partition."""
        cells = set(self.bucket_ids())
        return [
            entry
            for entry in catalog.values()
            if entry.role is CatalogRole.COMPOSITE and entry.members and set(entry.members) <= cells
        ]

    def as_payload(self, catalog: dict[str, CatalogEntry]) -> dict:
        """Server-owned shape the admin panel renders directly."""
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
