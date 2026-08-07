import inspect
from collections.abc import Callable
from dataclasses import dataclass, field

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

    is_time_dependent: bool = field(init=False)
    """Whether ``queryset`` accepts ``as_of``, read from its own signature at import.

    Derived rather than declared: a hand-maintained flag is a mapping that drifts from
    the function it describes, which is the same reason ``base_model`` is a model
    reference and not an enum (conventions §2).
    """

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_time_dependent", _accepts_as_of(self.queryset))

    def build(self, qs: QuerySet, *, as_of=None) -> QuerySet:
        """Evaluate the membership query, pinning time-dependent ones to ``as_of``.

        Every caller counting more than one entry must pass a single ``as_of`` for the
        whole computation (conventions §10). Without it each query calls
        ``timezone.now()`` separately, and over a multi-second request a user whose
        appointment ends mid-run can be counted in ``state__onboarding_booked`` by one
        bucket and ``state__onboarding_no_show`` by another — a self-inflicted overlap in
        a partition whose whole point is that there are none.
        """
        if as_of is not None and self.is_time_dependent:
            return self.queryset(qs, as_of=as_of)
        return self.queryset(qs)


def _accepts_as_of(queryset: Callable) -> bool:
    try:
        return "as_of" in inspect.signature(queryset).parameters
    except (TypeError, ValueError):  # builtins / C callables have no introspectable signature
        return False
