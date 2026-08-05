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
