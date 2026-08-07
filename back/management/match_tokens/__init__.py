"""Match success / token system — versioned rules for when a match has succeeded.

- **v0** — legacy ``completed_match`` heuristics. Comparison only; not activatable.
- **v1** (active) — tokens from total minutes of finished calls where both users were
  active. 8 tokens (≥ 205 minutes) = successful, and tokens keep accruing past that.

This is **domain logic, not analytics**: it defines what success *is*. Analytics packages
(``management.analytics``) may import it; it must not import them, or the match serializer
ends up pulling business rules out of a reporting package.

Public surface::

    from management.match_tokens import (
        ACTIVE_VERSION_ID,
        annotate_match_tokens,   # list views: one query for a whole page
        match_tokens,
        match_tokens_by_id,
        match_is_successful,
        successful_match_ids,    # the way to compare two versions in bulk
        success_target,
        get_version,
        list_versions,
    )
"""

from management.match_tokens.service import (
    ACTIVE_VERSION_ID,
    activatable_version_ids,
    annotate_match_tokens,
    get_version,
    list_versions,
    match_is_successful,
    match_tokens,
    match_tokens_by_id,
    match_total_minutes,
    success_target,
    successful_match_ids,
    tokens_from_total_minutes,
)

__all__ = [
    "ACTIVE_VERSION_ID",
    "activatable_version_ids",
    "annotate_match_tokens",
    "get_version",
    "list_versions",
    "match_is_successful",
    "match_tokens",
    "match_tokens_by_id",
    "match_total_minutes",
    "success_target",
    "successful_match_ids",
    "tokens_from_total_minutes",
]
