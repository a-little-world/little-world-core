"""Analytics for the management app.

``core/`` holds domain-agnostic machinery; each domain package (``signup/``, later
``match/``) holds its own queries, catalog, cohorts, and funnels; ``registry.py``
merges them and is the single lookup for the API.

See ``dev/docs/analytics_conventions.md`` and ``dev/docs/signup-funnel-analytics-refactor.md``.
"""

from management.analytics.signup.cohorts import SignupCohort, apply_cohort
from management.analytics.signup.funnels import SIGNUP_FUNNEL

__all__ = [
    "SIGNUP_FUNNEL",
    "SignupCohort",
    "apply_cohort",
]
