"""Shared shape for a match-success rule version."""

from collections.abc import Callable
from dataclasses import dataclass

from django.db.models import QuerySet

from management.models.matches import Match


@dataclass(frozen=True)
class SuccessVersion:
    """Immutable success rule set. Callers resolve through the registry.

    Two invariants, both enforced at construction:

    - **An activatable version is a token system.** Production callers ask for
      ``match_tokens`` unconditionally, so a version that cannot answer must not be
      selectable. ``v0`` is the exception and sets ``can_be_active=False``.
    - **Every version can answer in bulk.** ``successful_ids_fn`` takes a queryset, so
      comparing two versions across the whole match table is a handful of queries rather
      than one per match per version.
    """

    id: str
    title: str
    description: str
    is_successful_fn: Callable[[Match], bool]
    successful_ids_fn: Callable[[QuerySet], set[int]]
    tokens_fn: Callable[[Match], int] | None = None
    tokens_by_match_id_fn: Callable[[QuerySet], dict[int, int]] | None = None
    success_target: int | None = None
    can_be_active: bool = True
    """False for comparison-only versions. Selecting one as active fails at import."""

    def __post_init__(self) -> None:
        if self.can_be_active and (self.tokens_fn is None or self.success_target is None):
            raise ValueError(
                f"Match-success version {self.id!r} is activatable, so it must define both "
                f"tokens_fn and success_target. Set can_be_active=False for a "
                f"comparison-only version."
            )

    @property
    def uses_tokens(self) -> bool:
        """Derived, not stored — a flag beside the callable is a second source of truth."""
        return self.tokens_fn is not None

    def is_successful(self, match: Match) -> bool:
        return self.is_successful_fn(match)

    def successful_ids(self, qs: QuerySet) -> set[int]:
        """IDs of matches in ``qs`` that succeeded under this version."""
        return self.successful_ids_fn(qs)

    def tokens_for_match(self, match: Match) -> int:
        if self.tokens_fn is None:
            raise ValueError(
                f"Match-success version {self.id!r} is not a token system (see match_is_successful instead)."
            )
        return self.tokens_fn(match)

    def tokens_by_match_id(self, qs: QuerySet) -> dict[int, int]:
        if self.tokens_by_match_id_fn is None:
            raise ValueError(
                f"Match-success version {self.id!r} is not a token system (see successful_match_ids instead)."
            )
        return self.tokens_by_match_id_fn(qs)
