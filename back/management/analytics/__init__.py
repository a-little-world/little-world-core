"""Analytics for the management app.

``core/`` holds domain-agnostic machinery; each domain package (``user_journey/``, later
``match/``) holds its own queries, cohorts, catalog, funnels and partitions;
``registry.py`` merges them and is the single lookup for the API.

A domain is a **subject area over one entity**, not a chart. Signup analytics is not its
own domain — it is the first phase of the user journey over the same ``User``, so both
live in ``user_journey/`` and share their trait predicates.

See ``dev/docs/analytics_conventions.md`` and ``dev/docs/signup-funnel-analytics-refactor.md``.
"""

from management.analytics.user_journey.cohorts import PartitionCohort, SignupCohort, apply_cohort
from management.analytics.user_journey.funnels import SIGNUP_FUNNEL
from management.analytics.user_journey.partitions import USER_JOURNEY_V5

__all__ = [
    "SIGNUP_FUNNEL",
    "USER_JOURNEY_V5",
    "PartitionCohort",
    "SignupCohort",
    "apply_cohort",
]
