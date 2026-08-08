"""Shared shape for a match-outcome rule version."""

from collections.abc import Callable
from dataclasses import dataclass

from django.db.models import QuerySet

from management.models.matches import Match


@dataclass(frozen=True)
class MatchOutcomeVersion:
    """One versioned rule set for reading a match's outcome. Resolved via the registry.

    **Two separate concerns, deliberately.** Tokens are not success:

    - **Success** — did this match succeed? Required of every version, and the only thing
      the rest of the system asks. ``v0`` answers it from flags and interaction
      heuristics with no token scale at all; ``v1`` answers it from an off-platform flag
      *or* a token threshold. So a token count is at most one input to the rule, never
      the definition of it.
    - **Activity scale (tokens)** — how much did this match do? Optional, and useful in
      its own right: ``v1`` keeps accruing tokens long after the success threshold, which
      is how a 3,880-minute match stays distinguishable from a 205-minute one.

    Invariants, both enforced at construction:

    - **An activatable version must expose a token scale.** Not because success needs
      tokens, but because production surfaces a per-match token count unconditionally, so
      a selectable version has to be able to produce one. ``v0`` is the exception and
      sets ``can_be_active=False``.
    - **Success is stated once, as a queryset.** ``successful_matches_fn`` filters a
      queryset rather than returning IDs, so callers can compose it as a subquery; the row
      and ID forms are derived from it. A version that hand-wrote both a row form and a
      batch form had two answers to one question, which is the drift this package exists
      to prevent.
    """

    id: str
    title: str
    description: str

    # --- Success: the question the rest of the system asks. Required. ---
    successful_matches_fn: Callable[[QuerySet], QuerySet]

    # --- Activity scale: optional, and at most one input to the rule above. ---
    tokens_fn: Callable[[Match], int] | None = None
    tokens_by_match_id_fn: Callable[[QuerySet], dict[int, int]] | None = None
    success_token_threshold: int | None = None
    """Token count at which *this version's* success rule trips. None when it has no scale."""

    can_be_active: bool = True
    """False for comparison-only versions. Selecting one as active fails at import."""

    def __post_init__(self) -> None:
        if self.can_be_active and (self.tokens_fn is None or self.success_token_threshold is None):
            raise ValueError(
                f"Match-success version {self.id!r} is activatable, so it must define both "
                f"tokens_fn and success_token_threshold. Set can_be_active=False for a "
                f"comparison-only version."
            )

    @property
    def uses_tokens(self) -> bool:
        """Derived, not stored — a flag beside the callable is a second source of truth."""
        return self.tokens_fn is not None

    def successful_matches(self, qs: QuerySet) -> QuerySet:
        """The subset of ``qs`` that succeeded under this version, still a queryset.

        The **only** place a version states its success rule. The row and ID forms below
        are derived from it, because a second hand-written implementation is how the row
        answer starts disagreeing with the batch answer.
        """
        return self.successful_matches_fn(qs)

    def successful_ids(self, qs: QuerySet) -> set[int]:
        return set(self.successful_matches_fn(qs).values_list("id", flat=True))

    def is_successful(self, match: Match) -> bool:
        return self.successful_matches_fn(type(match).objects.filter(pk=match.pk)).exists()

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
