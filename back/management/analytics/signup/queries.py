"""Clean membership names for signup-funnel analytics.

Queries are single-purpose membership functions. Composition (unions, stage gates,
funnel order) lives in catalog / funnels — not inside these querysets.

Semantics today: **current-state snapshot** of a signup-date cohort.
"""

from django.db.models import Q, QuerySet

from management.api.user_advanced_filter import all_users
from management.api.user_journey_filters import (
    booked_onboarding_call,
    email_verified,
    never_active_or_deleted,
    no_show,
    self_onboarding_started_no_booked_call,
    too_low_german_level,
    user_deleted,
    user_form_completed_awaiting_onboarding,
    user_form_completed_excluding_a0_german,
)
from management.models.profile import Profile
from management.models.state import State

# ---------------------------------------------------------------------------
# Baseline / legacy stuck buckets (still used by journey lists & other charts)
# ---------------------------------------------------------------------------

users_all = all_users
users_never_active_or_deleted = never_active_or_deleted
users_who_no_showed_onboarding = no_show

users_with_verified_email_form_unfilled = email_verified
users_with_form_complete_awaiting_onboarding = user_form_completed_awaiting_onboarding
users_with_form_complete_awaiting_onboarding_excluding_a0_german = user_form_completed_excluding_a0_german
users_with_booked_onboarding_call = booked_onboarding_call
users_with_self_onboarding_started = self_onboarding_started_no_booked_call

# Global segment (cohort trait — not a funnel step)
learners_with_german_level_a0 = too_low_german_level

# ---------------------------------------------------------------------------
# Trait predicates (composable building blocks)
# ---------------------------------------------------------------------------


def learners_not_residing_in_germany(qs: QuerySet) -> QuerySet:
    """Learners whose country of residence is set and is not Germany."""
    return qs.filter(
        profile__user_type=Profile.TypeChoices.LEARNER,
        profile__country_of_residence__isnull=False,
    ).exclude(profile__country_of_residence=Profile.CountryChoices.GERMANY)


def _learners_form_complete_awaiting_onboarding_not_force_eligible(qs: QuerySet) -> QuerySet:
    """Shared base for onboarding-ineligibility reason subsets."""
    return qs.filter(
        is_active=True,
        profile__user_type=Profile.TypeChoices.LEARNER,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__is_onboarded=False,
        state__force_match_eligible=False,
        prematchingappointment__isnull=True,
    )


# ---------------------------------------------------------------------------
# Ineligibility reason subsets (form-complete context + one reason)
# ---------------------------------------------------------------------------


def learners_ineligible_for_onboarding_due_to_a0_german(qs: QuerySet) -> QuerySet:
    """Form-complete learners blocked from onboarding by A0 German level."""
    return _learners_form_complete_awaiting_onboarding_not_force_eligible(qs).filter(
        profile__lang_skill__contains=[
            {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
        ],
    )


def learners_ineligible_for_onboarding_due_to_residence_outside_germany(qs: QuerySet) -> QuerySet:
    """Form-complete learners blocked from onboarding by residence outside Germany.

    Learners with ``force_match_eligible=True`` are excluded (they bypass this check).
    """
    return learners_not_residing_in_germany(_learners_form_complete_awaiting_onboarding_not_force_eligible(qs))


# Reasons currently composing the onboarding-eligibility gate.
_ONBOARDING_INELIGIBILITY_REASONS = (
    learners_ineligible_for_onboarding_due_to_a0_german,
    learners_ineligible_for_onboarding_due_to_residence_outside_germany,
)


def learners_ineligible_for_onboarding(qs: QuerySet) -> QuerySet:
    """Union of active onboarding-ineligibility reasons (A0 German + outside Germany).

    ``force_match_eligible=True`` learners are never included — they bypass checks.

    Unions ``.values("id")`` rather than OR-ing the reason querysets: both traverse
    multi-valued relations, and OR-combining them reuses joins in ways that widen the
    result (conventions §6). ``.order_by()`` strips any inherited ordering — SQLite
    rejects ``ORDER BY`` inside a compound statement, so an ordered input would raise
    there while working on Postgres.
    """
    if not _ONBOARDING_INELIGIBILITY_REASONS:
        return qs.none()

    def reason_ids(reason) -> QuerySet:
        return reason(qs).order_by().values("id")

    id_qs = reason_ids(_ONBOARDING_INELIGIBILITY_REASONS[0])
    for reason in _ONBOARDING_INELIGIBILITY_REASONS[1:]:
        id_qs = id_qs.union(reason_ids(reason))
    return qs.filter(id__in=id_qs)


# ---------------------------------------------------------------------------
# Stage-reach queries (cumulative — bar count = query count)
# ---------------------------------------------------------------------------


def users_active_adjusted(qs: QuerySet) -> QuerySet:
    """Active registered accounts that are not deleted.

    Does **not** require email verification — that is the next funnel stage.
    (Previously this excluded never-verified users via ``never_active_or_deleted``,
    which made it nearly identical to ``users_who_verified_email``.)
    """
    return qs.filter(is_active=True).exclude(id__in=user_deleted(qs))


def users_who_verified_email(qs: QuerySet) -> QuerySet:
    """Active, non-deleted users who have verified their email."""
    return users_active_adjusted(qs).filter(state__email_authenticated=True)


def users_who_completed_form(qs: QuerySet) -> QuerySet:
    """Users who completed the registration form (includes A0 / outside-DE learners)."""
    return users_who_verified_email(qs).filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
    )


def users_eligible_for_onboarding(qs: QuerySet) -> QuerySet:
    """Form-complete users who are not blocked by an active ineligibility reason."""
    completed = users_who_completed_form(qs)
    return completed.exclude(id__in=learners_ineligible_for_onboarding(qs))


def users_who_started_onboarding(qs: QuerySet) -> QuerySet:
    """Users who started onboarding (booked call, self-onboarding, or already onboarded)."""
    return qs.filter(
        Q(state__is_onboarded=True) | Q(prematchingappointment__isnull=False) | Q(state__self_onboarding_started=True)
    ).distinct()


def users_who_are_onboarded(qs: QuerySet) -> QuerySet:
    """Users who completed onboarding."""
    return qs.filter(state__is_onboarded=True)
