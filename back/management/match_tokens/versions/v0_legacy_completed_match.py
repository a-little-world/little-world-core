"""v0 — legacy match success: ``completed_match`` in match_journey_filters.

**Comparison only.** This version is binary — it has no token scale, so there is no honest
answer to "how many tokens does this match have" under it. ``can_be_active=False`` makes
selecting it as the production rule fail at import rather than at the first caller that
asks for a token count.

A match succeeds under **either** path below (temporary matches excluded from the flag
path). Kept so the impact of the token rules can be measured against what came before.

**Postgres only.** ``completed_match`` extracts days from a datetime difference, which
SQLite cannot do — calling this version on a SQLite run raises
``ValueError: Extract requires native DurationField database support``. That is another
reason it is not activatable: the active version has to work everywhere the app runs.

**Path A — explicit flags**
  ``completed=True`` or ``completed_off_plattform=True`` (excludes ``match_type=TEMPORARY``).

**Path B — interaction heuristics** (defaults from ``completed_match``)
  All of:
  - still ``active=True``, not support matching
  - at least one message each way (user1→user2 and user2→user1)
  - ``total_messages_counter`` ≥ 2
  - ``total_mutal_video_calls_counter`` ≥ 1
  - contact span (``latest_interaction_at - created_at``) ≥ 28 days (4 weeks)
  - last interaction ≥ 21 days ago (``LAST_INTERACTION_DAYS``)
"""

from django.db.models import QuerySet

from management.match_tokens.versions.base import SuccessVersion
from management.models.matches import Match

VERSION_ID = "v0"

# Mirrors completed_match() defaults — documented here so the version states its criteria
# without readers having to open the filter. If those defaults change, update this
# module's docstring and description in the same change.
_MIN_MUTUAL_MESSAGES = 2
_MIN_MUTUAL_VIDEO_CALLS = 1
_CONTACT_SPAN_DAYS = 4 * 7  # 28 days
_DAYS_SINCE_LAST_INTERACTION = 21  # LAST_INTERACTION_DAYS


def successful_ids(qs: QuerySet) -> set[int]:
    """One query for the whole queryset — ``completed_match`` is already a filter.

    The per-match form used to re-run this filter once per row, which made a full
    comparison against v1 take ~0.7s per match.
    """
    # Lazy import: match_journey_filters imports match_is_successful from this package.
    from management.api.match_journey_filters import completed_match

    return set(completed_match(qs).values_list("id", flat=True))


def is_successful(match) -> bool:
    return bool(successful_ids(Match.objects.filter(pk=match.pk)))


VERSION = SuccessVersion(
    id=VERSION_ID,
    title="Legacy completed_match (v0)",
    description=(
        "Pre-token success from match_journey_filters.completed_match. Succeeds if "
        "(A) completed or completed_off_plattform is set (non-temporary), or (B) the "
        f"match is still active, non-support, has ≥{_MIN_MUTUAL_MESSAGES} mutual "
        f"messages and ≥{_MIN_MUTUAL_VIDEO_CALLS} mutual video call, messages both "
        f"ways, contact span ≥{_CONTACT_SPAN_DAYS} days (4 weeks), and last "
        f"interaction ≥{_DAYS_SINCE_LAST_INTERACTION} days ago. Not a token system; "
        "comparison only."
    ),
    is_successful_fn=is_successful,
    successful_ids_fn=successful_ids,
    can_be_active=False,
)
