"""Cumulative stage-reach queries — the ``funnel__`` namespace.

Each query counts everyone who **reached at least** that stage, so the stages nest:
`active ⊇ email verified ⊇ form completed ⊇ eligible`. That nesting is what makes the
bar chart monotonic, and it is the reason these cannot be reused as partition cells —
see ``queries/state.py`` for the mutually exclusive versions.

Queries are single-purpose membership functions. Composition (unions, stage gates,
funnel order) lives in catalog / funnels, not inside these querysets.

Semantics: **current-state snapshot** of a signup-date cohort.
"""

from django.db.models import Q, QuerySet

from management.analytics.user_journey.queries import traits
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
from management.self_onboarding_progress import self_onboarding_started_q

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
# Ineligibility (context + shared reason predicates)
# ---------------------------------------------------------------------------


def _form_complete_awaiting_onboarding(qs: QuerySet) -> QuerySet:
    """Context the funnel asks its ineligibility questions in.

    Deliberately *not* shared with the partition. The funnel needs a cumulative gate
    (verified, form filled, not yet onboarded); the partition needs mutually exclusive
    cells and applies its own context. Only the reason predicates are shared.
    """
    return qs.filter(
        Q(is_active=True)
        & traits.is_learner()
        & Q(
            state__user_form_state=traits.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__is_onboarded=False,
            state__force_match_eligible=False,
            # Multi-valued relation, but `isnull=True` matches zero joined rows, so this
            # cannot fan out and the OR below stays safe (conventions §6).
            prematchingappointment__isnull=True,
        )
    )


def learners_not_residing_in_germany(qs: QuerySet) -> QuerySet:
    """Learners whose country of residence is set and is not Germany."""
    return qs.filter(traits.is_learner() & traits.resides_outside_germany())


def learners_ineligible_for_onboarding_due_to_a0_german(qs: QuerySet) -> QuerySet:
    """Form-complete learners blocked from onboarding by A0 German level."""
    return _form_complete_awaiting_onboarding(qs).filter(traits.has_a0_german())


def learners_ineligible_for_onboarding_due_to_residence_outside_germany(qs: QuerySet) -> QuerySet:
    """Form-complete learners blocked from onboarding by residence outside Germany.

    Learners with ``force_match_eligible=True`` are excluded (they bypass this check).
    """
    return _form_complete_awaiting_onboarding(qs).filter(traits.resides_outside_germany())


def learners_ineligible_for_onboarding(qs: QuerySet) -> QuerySet:
    """Union of the active onboarding-ineligibility reasons.

    Reasons come from ``traits.INELIGIBILITY_REASONS``, so the funnel gate and the
    partition's ``state__onboarding_ineligible`` bucket can never answer "is this learner
    blocked?" differently.

    The reasons are ``Q`` objects OR-ed inside one ``filter()`` rather than separate
    querysets combined afterwards. Every reason reads single-valued ``profile`` columns,
    so this adds no join and cannot widen the result the way OR-ing two independently
    filtered querysets does (conventions §6).
    """
    reasons = list(traits.INELIGIBILITY_REASONS.values())
    if not reasons:
        return qs.none()

    combined = reasons[0]
    for reason in reasons[1:]:
        combined |= reason
    return _form_complete_awaiting_onboarding(qs).filter(combined)


# ---------------------------------------------------------------------------
# Stage-reach queries (cumulative — bar count = query count)
# ---------------------------------------------------------------------------


def users_active_adjusted(qs: QuerySet) -> QuerySet:
    """Active registered accounts that are not deleted.

    Does **not** require email verification — that is the next funnel stage.
    Unresponsive users are kept: they did reach this stage, and a cumulative funnel
    counts reach, not current standing. (``state.live_users`` excludes them because a
    partition needs somewhere exclusive to put them.)
    """
    return qs.filter(is_active=True).exclude(id__in=user_deleted(qs))


def users_who_verified_email(qs: QuerySet) -> QuerySet:
    """Active, non-deleted users who have verified their email."""
    return users_active_adjusted(qs).filter(state__email_authenticated=True)


def users_who_completed_form(qs: QuerySet) -> QuerySet:
    """Users who completed the registration form (includes A0 / outside-DE learners).

    Built on ``users_who_verified_email`` so the stage nests inside the one before it.
    """
    return users_who_verified_email(qs).filter(state__user_form_state=traits.FILLED)


def users_eligible_for_onboarding(qs: QuerySet) -> QuerySet:
    """Form-complete users who are not blocked by an active ineligibility reason."""
    return users_who_completed_form(qs).exclude(id__in=learners_ineligible_for_onboarding(qs))


def users_who_started_onboarding(qs: QuerySet) -> QuerySet:
    """Users who started onboarding (booked call, self-onboarding, or already onboarded)."""
    return qs.filter(
        Q(state__is_onboarded=True) | Q(prematchingappointment__isnull=False) | self_onboarding_started_q()
    ).distinct()


def users_who_are_onboarded(qs: QuerySet) -> QuerySet:
    """Users who completed onboarding."""
    return qs.filter(state__is_onboarded=True)
