"""Clean membership names for signup-funnel querysets.

Delegates to legacy ``user_journey_filters`` / ``user_advanced_filter`` so
behaviour stays identical during the structural migration.
"""

from django.db.models import QuerySet

from management.api.user_advanced_filter import all_users
from management.api.user_journey_filters import (
    booked_onboarding_call,
    email_verified,
    never_active_or_deleted,
    no_show,
    self_onboarding_started_no_booked_call,
    too_low_german_level,
    user_form_completed,
)
from management.models.profile import Profile
from management.models.state import State

# Baseline
users_all = all_users

# Dropouts / early exits
users_never_active_or_deleted = never_active_or_deleted
users_who_no_showed_onboarding = no_show

# Signup stages (current-state membership)
users_with_verified_email_form_unfilled = email_verified
users_with_form_complete_no_onboarding_call = user_form_completed
users_with_booked_onboarding_call = booked_onboarding_call
users_with_self_onboarding_started = self_onboarding_started_no_booked_call

# Segments (cohort traits — kept for cohort pre-filtering only, not funnel steps)
learners_with_german_level_a0 = too_low_german_level


def learners_ineligible_for_onboarding(qs: QuerySet) -> QuerySet:
    """Learners who completed the form but cannot proceed to onboarding due to German level.

    Specifically: form filled, email verified, not onboarded, no appointment booked
    or attended, German skill A0 (below B1), and ``force_match_eligible=False``.

    Learners with ``force_match_eligible=True`` bypass the language check and are
    therefore excluded — they can proceed to onboarding regardless of level.

    This is a true funnel dropout — a partition of form-complete learners who are
    ineligible for onboarding. It is *not* the global A0 segment.
    """
    a0_german = {
        "profile__user_type": Profile.TypeChoices.LEARNER,
        "profile__lang_skill__contains": [
            {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
        ],
    }
    return qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__is_onboarded=False,
        state__force_match_eligible=False,
        **a0_german,
    )
