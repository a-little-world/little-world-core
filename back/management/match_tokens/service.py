"""Caller-facing helpers. Prefer these over importing a specific version module.

Every helper takes an optional ``version``; omitting it uses the active one. The
queryset-shaped helpers are the ones to reach for in a list view or an export — the
per-match helpers cost a query each unless the queryset was annotated first.
"""

from django.db.models import QuerySet

from management.match_tokens.sessions import annotate_total_call_minutes, total_call_minutes
from management.match_tokens.versions import (
    ACTIVE_VERSION_ID,
    activatable_version_ids,
    get_version,
    list_versions,
)
from management.match_tokens.versions.v1_total_minutes import tokens_from_total_minutes


def success_target(version: str | None = None) -> int:
    """Token success threshold. Only defined for token-based versions."""
    resolved = get_version(version)
    if resolved.success_target is None:
        raise ValueError(f"Match-success version {resolved.id!r} has no token target (use match_is_successful).")
    return resolved.success_target


def match_tokens(match, version: str | None = None) -> int:
    """Tokens earned under a token-based version (default: active).

    Costs one query per call unless ``match`` came from a queryset passed through
    ``annotate_match_tokens``. Use ``match_tokens_by_id`` for more than a couple of rows.
    """
    return get_version(version).tokens_for_match(match)


def match_tokens_by_id(qs: QuerySet, version: str | None = None) -> dict[int, int]:
    """Match ID → tokens, for every match in ``qs``. One query."""
    return get_version(version).tokens_by_match_id(qs)


def match_is_successful(match, version: str | None = None) -> bool:
    """Whether the match counts as successful under the given (or active) version."""
    return get_version(version).is_successful(match)


def successful_match_ids(qs: QuerySet, version: str | None = None) -> set[int]:
    """IDs of the matches in ``qs`` that succeeded. The way to compare two versions."""
    return get_version(version).successful_ids(qs)


def annotate_match_tokens(qs: QuerySet) -> QuerySet:
    """Pre-load the token input for a whole queryset so per-row lookups are free.

    Call this in a list view's ``get_queryset``; ``match_tokens`` then reads the
    annotation instead of querying per row.
    """
    return annotate_total_call_minutes(qs)


def match_total_minutes(match) -> float:
    """Total minutes from finished mutual sessions — the input to v1 banding."""
    return total_call_minutes(match)


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
