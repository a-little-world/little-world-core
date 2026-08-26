"""Predicates shared by the signup funnel and the current-state partition.

A trait is a property of a user that both constructs need to ask about. Only the
predicate lives here — never the context it is asked in. The funnel and the partition
apply genuinely different contexts and must not be forced to share them (see
``queries/__init__.py``).

Everything here is a ``Q``, not a ``QuerySet``, so a caller composes it into whatever
base it already has instead of re-filtering.
"""

import json

from django.db.models import JSONField
from django.db.models import Q
from django.db.models.lookups import Lookup

from management.models.profile import Profile
from management.models.state import State

FILLED = State.UserFormStateChoices.FILLED
UNFILLED = State.UserFormStateChoices.UNFILLED
SEARCHING = State.SearchingStateChoices.SEARCHING
IDLE = State.SearchingStateChoices.IDLE

class JSONArrayContainsObject(Lookup):
    """Test whether a JSON array contains an object with the requested key/value pairs."""

    lookup_name = "array_contains_object"
    prepare_rhs = False

    def as_postgresql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        return f"{lhs} @> %s::jsonb", [*lhs_params, json.dumps([self.rhs])]

    def as_sqlite(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        comparisons = []
        params = list(lhs_params)
        for key, value in self.rhs.items():
            path = f"$.{json.dumps(str(key))}"
            comparisons.append("JSON_EXTRACT(item.value, %s) = JSON_EXTRACT(%s, '$')")
            params.extend((path, json.dumps(value)))

        if not comparisons:
            return f"JSON_TYPE({lhs}) = 'array'", params

        sql = f"EXISTS (SELECT 1 FROM JSON_EACH({lhs}) AS item WHERE {' AND '.join(comparisons)})"
        return sql, params


JSONField.register_lookup(JSONArrayContainsObject)


A0_GERMAN = {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}


def is_learner() -> Q:
    return Q(profile__user_type=Profile.TypeChoices.LEARNER)


def is_volunteer() -> Q:
    return Q(profile__user_type=Profile.TypeChoices.VOLUNTEER)


def has_a0_german() -> Q:
    """Claims German at level 0."""
    return Q(profile__lang_skill__array_contains_object=A0_GERMAN)


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
