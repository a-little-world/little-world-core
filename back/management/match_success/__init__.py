"""Versioned rules for reading a match's outcome. The single definition of match success.

**Two concerns, and tokens are not the headline one.** A version answers:

- *Did this match succeed?* — required of every version, and what the rest of the system
  asks. It is **not** "tokens ≥ N": ``v0`` answers with no token scale at all, and ``v1``
  answers with an off-platform flag *or* a token threshold. Tokens are one possible input.
- *How much did this match do?* — the token scale. Optional, and valuable separately:
  ``v1`` keeps accruing past success so a long-running match stays distinguishable.

The package is named for the first. It used to be called ``match_tokens``, which read as
though the token count *were* the success rule — it is not, and both versions prove it.

Registered versions:

- **v0** — legacy ``completed_match`` heuristics. Comparison only; not activatable.
- **v1** (active) — off-platform completion, or ≥ 205 minutes of finished mutual calls
  (8 tokens). Tokens keep accruing past that, one per further 30 minutes.

This is **domain logic, not analytics**: it defines what success *is*. Analytics packages
(``management.analytics``) may import it; it must not import them, or the match serializer
ends up pulling business rules out of a reporting package.

Public surface::

    from management.match_success import (
        ACTIVE_VERSION_ID,
        # success — ask these, not the token count
        match_is_successful,
        successful_matches,      # composable as a subquery
        successful_match_ids,    # the way to compare two versions in bulk
        # activity scale
        annotate_match_tokens,   # list views: one query for a whole page
        match_tokens,
        match_tokens_by_id,
        success_token_threshold,
        get_version,
        list_versions,
    )
"""

from management.match_success.service import (
    ACTIVE_VERSION_ID,
    activatable_version_ids,
    annotate_match_tokens,
    get_version,
    list_versions,
    match_is_successful,
    match_tokens,
    match_tokens_by_id,
    match_total_minutes,
    success_token_threshold,
    successful_match_ids,
    successful_matches,
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
    "success_token_threshold",
    "successful_match_ids",
    "successful_matches",
    "tokens_from_total_minutes",
]
