"""Cohort specs for the user-journey domain.

Both constructs count a signup-date cohort, so they share date-bound handling.
They differ on segment gates, and those differences are deliberate — see
``PartitionCohort``.
"""

from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Model, QuerySet

from management.analytics.core.cohorts import CohortSpec
from management.analytics.core.display_time import inclusive_range
from management.analytics.user_journey.queries import traits
from management.models.profile import Profile
from management.models.user import User


@dataclass(frozen=True)
class SignupCohort:
    """Universe of users for signup funnel counting — applied once before buckets.

    Range semantics: **joined within the range**, both bounds inclusive, interpreted in
    the display timezone (conventions §10). Callers should validate and parse request
    input before constructing this — the view owns transport (§11).
    """

    start_date: date | datetime | str
    end_date: date | datetime | str
    volunteers_only: bool = False
    include_too_low_german_level: bool = True

    @property
    def base_model(self) -> type[Model]:
        return User

    def apply(self, qs: QuerySet) -> QuerySet:
        """Filter to signup-date cohort and optional segment gates."""
        start, end = inclusive_range(self.start_date, self.end_date)

        qs = qs.filter(date_joined__range=[start, end])

        if self.volunteers_only:
            qs = qs.filter(traits.is_volunteer())

        if not self.include_too_low_german_level:
            qs = qs.exclude(traits.is_learner() & traits.has_a0_german())

        return qs


@dataclass(frozen=True)
class PartitionCohort:
    """Universe of users for the user-journey partition.

    Same date semantics as ``SignupCohort``, minus the ``include_too_low_german_level``
    toggle. The partition gives A0-German and outside-Germany learners their own cells
    (``state__onboarding_ineligible``, ``state__search_blocked``), so dropping them from
    the universe would hide the very numbers those cells exist to surface — and would
    leave the partition unable to balance against ``funnel__all``.

    ``user_type`` is the optional segment gate (``learner`` / ``volunteer``). Omit it
    for the whole signup-date universe; it is a cohort filter, never a partition cell
    (conventions §17).
    """

    start_date: date | datetime | str
    end_date: date | datetime | str
    user_type: str | None = None

    def __post_init__(self):
        if self.user_type is None:
            return
        if self.user_type not in Profile.TypeChoices.values:
            raise ValueError(f"user_type must be one of {sorted(Profile.TypeChoices.values)}, not {self.user_type!r}.")

    @property
    def base_model(self) -> type[Model]:
        return User

    def apply(self, qs: QuerySet) -> QuerySet:
        start, end = inclusive_range(self.start_date, self.end_date)

        qs = qs.filter(date_joined__range=[start, end])

        if self.user_type == Profile.TypeChoices.VOLUNTEER:
            qs = qs.filter(traits.is_volunteer())
        elif self.user_type == Profile.TypeChoices.LEARNER:
            qs = qs.filter(traits.is_learner())

        return qs


def apply_cohort(qs: QuerySet, spec: CohortSpec) -> QuerySet:
    """Apply any ``CohortSpec`` implementation to a queryset."""
    return spec.apply(qs)
