"""Predicates shared by the signup funnel and the current-state partition.

A trait is a property of a user that both constructs need to ask about. Only the
predicate lives here — never the context it is asked in. The funnel and the partition
apply genuinely different contexts and must not be forced to share them (see
``queries/__init__.py``).

Everything here is a ``Q``, not a ``QuerySet``, so a caller composes it into whatever
base it already has instead of re-filtering.
"""

from django.db import connection
from django.db.models import JSONField, Q
from django.db.models.lookups import Lookup

from management.models.profile import Profile
from management.models.state import State

FILLED = State.UserFormStateChoices.FILLED
UNFILLED = State.UserFormStateChoices.UNFILLED
SEARCHING = State.SearchingStateChoices.SEARCHING
IDLE = State.SearchingStateChoices.IDLE

A0_GERMAN = [{"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}]


class SQLiteHasA0German(Lookup):
    """SQLite equivalent of ``lang_skill__contains=A0_GERMAN``."""

    lookup_name = "has_a0_german"
    prepare_rhs = False

    def as_sqlite(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        sql = (
            f"EXISTS (SELECT 1 FROM JSON_EACH({lhs}) AS item "
            "WHERE JSON_EXTRACT(item.value, '$.lang') = %s "
            "AND JSON_EXTRACT(item.value, '$.level') = %s)"
        )
        return sql, [*lhs_params, A0_GERMAN[0]["lang"], A0_GERMAN[0]["level"]]


JSONField.register_lookup(SQLiteHasA0German)


def is_learner() -> Q:
    return Q(profile__user_type=Profile.TypeChoices.LEARNER)


def is_volunteer() -> Q:
    return Q(profile__user_type=Profile.TypeChoices.VOLUNTEER)


def has_a0_german() -> Q:
    """Claims German at level 0."""
    if connection.features.supports_json_field_contains:
        return Q(profile__lang_skill__contains=A0_GERMAN)
    return Q(profile__lang_skill__has_a0_german=True)


def resides_outside_germany() -> Q:
    """Country of residence is **set** and is not Germany.

    The ``isnull=False`` half is load-bearing. A bare negation matches NULL rows, which
    is how ``user_journey_filters.exclude_match_ineligible_learners`` ends up treating
    every learner who never answered the question as ineligible.
    """
    return Q(profile__country_of_residence__isnull=False) & ~Q(
        profile__country_of_residence=Profile.CountryChoices.GERMANY
    )


def is_match_ineligible_learner() -> Q:
    """Learner blocked from matching by German level or residence.

    ``force_match_eligible`` is an explicit staff override and bypasses both reasons.
    The reasons themselves are enumerated in ``INELIGIBILITY_REASONS`` so the funnel can
    break them out for drill-down while the partition only needs the union.
    """
    return is_learner() & Q(state__force_match_eligible=False) & (has_a0_german() | resides_outside_germany())


# Reason label → predicate. Extending the gate means adding here, not editing callers.
INELIGIBILITY_REASONS: dict[str, Q] = {
    "a0_german": is_learner() & Q(state__force_match_eligible=False) & has_a0_german(),
    "outside_germany": is_learner() & Q(state__force_match_eligible=False) & resides_outside_germany(),
}
