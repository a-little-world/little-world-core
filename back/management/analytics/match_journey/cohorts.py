"""Cohort specs for the match-journey domain."""

from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Model, QuerySet

from management.analytics.core.display_time import inclusive_range
from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType

JOURNEY_MATCH_TYPES = frozenset({MatchType.STANDARD, MatchType.RANDOM_CALL})


@dataclass(frozen=True)
class MatchPartitionCohort:
    """Universe of matches for the V5 partition.

    Always non-support Standard and Random Call (not TEMPORARY). Optional ``created_at``
    bounds (both inclusive in the display timezone). Omit both dates for all-time.

    ``match_type`` is the optional source gate (``standard`` / ``random_call``). Omit it
    for both journey types; it is a cohort filter, never a partition cell
    (conventions §17). ``temporary`` is not a valid value — those rows are outside the
    universe.
    """

    start_date: date | datetime | str | None = None
    end_date: date | datetime | str | None = None
    match_type: str | None = None

    def __post_init__(self):
        if self.match_type is None:
            return
        if self.match_type not in JOURNEY_MATCH_TYPES:
            raise ValueError(f"match_type must be one of {sorted(JOURNEY_MATCH_TYPES)}, not {self.match_type!r}.")

    @property
    def base_model(self) -> type[Model]:
        return Match

    def apply(self, qs: QuerySet) -> QuerySet:
        qs = qs.filter(Match.journey_q())
        if self.match_type is not None:
            qs = qs.filter(match_type=self.match_type)
        if self.start_date is None and self.end_date is None:
            return qs
        if self.start_date is None or self.end_date is None:
            raise ValueError("MatchPartitionCohort requires both start_date and end_date, or neither.")
        start, end = inclusive_range(self.start_date, self.end_date)
        return qs.filter(created_at__range=[start, end])
