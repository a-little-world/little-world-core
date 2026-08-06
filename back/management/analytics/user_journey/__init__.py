"""User-journey analytics: one user's path through the product, end to end.

Covers everything from account creation to leaving the platform, in two constructs
over the same signup-date cohort:

- ``funnels.SIGNUP_FUNNEL`` — cumulative stage reach, the ``signup__`` namespace.
- ``partitions.USER_JOURNEY_V5`` — mutually exclusive current state, the ``current__``
  namespace. Replaces the ``journey_v2__*`` buckets rendered as "The User Journey V4"
  in the admin panel; V4 itself is left untouched.

Signup used to be a separate domain. It is not one: it is the first phase of this
journey over the same entity, and splitting it produced two homes for shared predicates
like "is this learner blocked from matching?". The two constructs still need different
queries — a funnel must nest, a partition must not overlap — but they now compose the
same traits. See ``queries/__init__.py`` and ``dev/docs/analytics_conventions.md`` §17.
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
