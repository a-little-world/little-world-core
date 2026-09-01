"""Cohort specs for the match-journey domain."""

from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Model, QuerySet

from management.analytics.core.display_time import inclusive_range
from management.models.matches import Match


@dataclass(frozen=True)
class MatchPartitionCohort:
    """Universe of matches for the V5 partition.

    Always non-support Standard and Random Call (not TEMPORARY). Optional ``created_at``
    bounds (both inclusive in the display timezone). Omit both dates for all-time.
    """

    start_date: date | datetime | str | None = None
    end_date: date | datetime | str | None = None

    @property
    def base_model(self) -> type[Model]:
        return Match

    def apply(self, qs: QuerySet) -> QuerySet:
        qs = qs.filter(Match.journey_q())
        if self.start_date is None and self.end_date is None:
            return qs
        if self.start_date is None or self.end_date is None:
            raise ValueError("MatchPartitionCohort requires both start_date and end_date, or neither.")
        start, end = inclusive_range(self.start_date, self.end_date)
        return qs.filter(created_at__range=[start, end])
