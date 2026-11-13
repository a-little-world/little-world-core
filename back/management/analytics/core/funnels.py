"""Domain-agnostic funnel definition types."""

from dataclasses import dataclass
from enum import StrEnum

from django.db.models import Model

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.roles import CatalogRole


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
    label_override: str | None = None
    description_override: str | None = None


@dataclass(frozen=True)
class FunnelDefinition:
    id: str
    title: str
    mode: FunnelMode
    base_model: type[Model]
    steps: tuple[FunnelStep, ...]
    merge_groups: tuple[FunnelMergeGroup, ...] = ()

    def list_ids(self) -> list[str]:
        return [step.list_id for step in self.steps]

    def display_meta(self, catalog: dict[str, CatalogEntry]) -> dict[str, dict[str, str]]:
        """Map list_id (and merge keys) → {label, description?} for the chart."""
        meta: dict[str, dict[str, str]] = {}
        for step in self.steps:
            entry = catalog[step.list_id]
            label = step.label_override or entry.display_name
            description = step.description_override or entry.description
            meta_entry: dict[str, str] = {"label": label}
            if description:
                meta_entry["description"] = description
            meta[step.list_id] = meta_entry
        for group in self.merge_groups:
            entry = {"label": group.display_label}
            if group.description:
                entry["description"] = group.description
            meta[group.merge_key] = entry
        return meta
