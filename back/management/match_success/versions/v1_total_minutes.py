"""v1 — tokens from total finished mutual call minutes (active).

Only sessions where both users were active count. Minutes are summed across those calls,
then mapped through the bands below. 8 tokens = successful match.

Bands (total minutes)::

    < 25      → 0
    25–54     → 1
    55–79     → 2
    80–104    → 3
    105–129   → 4
    130–154   → 5
    155–179   → 6
    180–204   → 7
    ≥ 205     → 8  (= match successful)

**Accrual does not stop at success.** Past 205 minutes every further 30 minutes earns
another token, so a pair still meeting weekly keeps scoring and a 3,880-minute match is
not indistinguishable from a 205-minute one. Success is the threshold (``tokens >= 8``),
not the top of the scale.

Thresholds are listed explicitly so tweaks stay reviewable. When the meaning of a band
changes enough to break comparisons, add a new version rather than editing history here.
"""

from datetime import timedelta

from django.db.models import Q, QuerySet

from management.match_success.sessions import (
    TOTAL_CALL_TIME_ANNOTATION,
    annotate_total_call_minutes,
    total_call_minutes,
    total_call_minutes_by_match_id,
)
from management.match_success.versions.base import MatchOutcomeVersion

VERSION_ID = "v1"

# (minimum total minutes inclusive → tokens). Ordered ascending; the last entry is the
# success threshold and the point where linear accrual takes over.
MINUTE_TOKEN_THRESHOLDS: tuple[tuple[float, int], ...] = (
    (25, 1),
    (55, 2),
    (80, 3),
    (105, 4),
    (130, 5),
    (155, 6),
    (180, 7),
    (205, 8),
)

# `tokens_from_total_minutes` walks the table in order and stops at the first band the
# total does not reach, so an out-of-order entry would silently return a wrong token count.
if [minutes for minutes, _ in MINUTE_TOKEN_THRESHOLDS] != sorted(minutes for minutes, _ in MINUTE_TOKEN_THRESHOLDS):
    raise ValueError("MINUTE_TOKEN_THRESHOLDS must be ordered by ascending minutes")

SUCCESS_MINUTES, SUCCESS_TOKEN_THRESHOLD = MINUTE_TOKEN_THRESHOLDS[-1]

#: Minutes per additional token once the success threshold is reached.
MINUTES_PER_TOKEN_AFTER_SUCCESS = 30


def tokens_from_total_minutes(total_minutes: float) -> int:
    """Map aggregated mutual call minutes to tokens. Pure — safe for unit tests."""
    if total_minutes >= SUCCESS_MINUTES:
        beyond = total_minutes - SUCCESS_MINUTES
        return SUCCESS_TOKEN_THRESHOLD + int(beyond // MINUTES_PER_TOKEN_AFTER_SUCCESS)

    tokens = 0
    for minimum, value in MINUTE_TOKEN_THRESHOLDS:
        if total_minutes < minimum:
            break
        tokens = value
    return tokens


def tokens_for_match(match) -> int:
    return tokens_from_total_minutes(total_call_minutes(match))


def tokens_by_match_id(qs: QuerySet) -> dict[int, int]:
    return {
        match_id: tokens_from_total_minutes(minutes) for match_id, minutes in total_call_minutes_by_match_id(qs).items()
    }


def successful_matches(qs: QuerySet) -> QuerySet:
    """The subset of ``qs`` that succeeded, as a queryset.

    Two ways to succeed, and both belong here rather than in whichever chart happens to
    ask. ``completed_off_plattform`` is an explicit signal that the pair carried on
    away from the platform: the minute bands structurally cannot see those calls, so
    without this arm a successful off-platform match reads as a failure.

    Expressed as a filter rather than an ID set so callers can compose it as a subquery —
    ``user_journey`` asks "is this user in a successful match?" per row, and inlining
    ~900 IDs into that predicate would be silly. ``>= SUCCESS_MINUTES`` is exactly
    ``tokens >= SUCCESS_TOKEN_THRESHOLD`` by the banding above.
    """
    return annotate_total_call_minutes(qs).filter(
        Q(completed_off_plattform=True)
        | Q(**{f"{TOTAL_CALL_TIME_ANNOTATION}__gte": timedelta(minutes=SUCCESS_MINUTES)})
    )


VERSION = MatchOutcomeVersion(
    id=VERSION_ID,
    title="Total mutual call minutes (v1)",
    description=(
        "Sum minutes from finished LiveKit sessions where both users were active, then "
        f"apply the minute→token bands. {SUCCESS_TOKEN_THRESHOLD} tokens (≥ {SUCCESS_MINUTES:g} minutes) = "
        f"successful, as is an explicit off-platform completion. Tokens keep accruing "
        f"after that, one per further {MINUTES_PER_TOKEN_AFTER_SUCCESS} minutes."
    ),
    successful_matches_fn=successful_matches,
    tokens_fn=tokens_for_match,
    tokens_by_match_id_fn=tokens_by_match_id,
    success_token_threshold=SUCCESS_TOKEN_THRESHOLD,
    details={
        "token_bands": [{"min_minutes": minutes, "tokens": tokens} for minutes, tokens in MINUTE_TOKEN_THRESHOLDS],
        "success_minutes": SUCCESS_MINUTES,
        "minutes_per_token_after_success": MINUTES_PER_TOKEN_AFTER_SUCCESS,
    },
)
