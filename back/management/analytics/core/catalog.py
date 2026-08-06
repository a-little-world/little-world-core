from collections.abc import Callable
from dataclasses import dataclass

from django.db.models import Model, QuerySet

from management.analytics.core.roles import CatalogRole


@dataclass(frozen=True)
class CatalogEntry:
    """Stable list ID → membership query + role for one analytics entity."""

    list_id: str
    role: CatalogRole
    queryset: Callable[[QuerySet], QuerySet]
    description: str
    display_name: str
    base_model: type[Model]
    members: tuple[str, ...] = ()
    """Catalog IDs this entry rolls up, for ``COMPOSITE`` entries only.

    Declaring them lets the registry check that the members are disjoint and sum back to
    the composite, so a rollup cannot quietly drift away from its parts. A composite with
    no members declared is not checked — which is why the registry requires them.
    """
