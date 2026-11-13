from typing import Protocol

from django.db.models import Model, QuerySet


class CohortSpec(Protocol):
    """Entity-specific universe filter applied once before bucketing."""

    base_model: type[Model]

    def apply(self, qs: QuerySet) -> QuerySet: ...
