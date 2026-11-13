import pgeocode
from django.db import models

from management.models.profile import Profile
from management.permissions import ManagementPermission


class AudienceFilters(models.TextChoices):
    LEARNERS_WITH_A1A2 = "learners_with_a1a2", "Learners with A1/A2 German"
    LEARNERS_ABOVE_A1A2 = "learners_above_a1a2", "Learners above A1/A2"
    VOLUNTEERS = "volunteers", "All registered volunteers"
    LEARNERS = "learners", "All registered learners"
    ONBOARDED_VOLUNTEERS = "onboarded_volunteers", "Onboarded volunteers"
    ONBOARDED_LEARNERS = "onboarded_learners", "Onboarded learners"
    LEARNERS_OUTSIDE_GERMANY = "learners_outside_germany", "Learners outside Germany"
    RANDOM_CALL_USERS = "random_call_users", "Random-call users"
    MATCH_ELIGIBLE_USERS = "match_eligible_users", "Match-eligible users"
    NRW_RESIDENTS = "nrw_residents", "NRW residents"
    NONE = "none", "None"


def filter__learners_with_a1a2(user):
    if user.state.force_match_eligible:
        return False
    lang_skill_german = list(filter(lambda x: x["lang"] == "german", user.profile.lang_skill))
    german_level = lang_skill_german[0]["level"] if len(lang_skill_german) > 0 else Profile.LanguageSkillChoices.LEVEL_0
    has_a1a2 = german_level == Profile.LanguageSkillChoices.LEVEL_0
    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and has_a1a2


def filter__learners_above_a1a2(user):
    lang_skill_german = list(filter(lambda x: x["lang"] == "german", user.profile.lang_skill))
    german_level = lang_skill_german[0]["level"] if len(lang_skill_german) > 0 else Profile.LanguageSkillChoices.LEVEL_0
    better_than_a1a2 = german_level != Profile.LanguageSkillChoices.LEVEL_0 or user.state.force_match_eligible

    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and better_than_a1a2


def filter__volunteers(user):
    return user.profile.user_type == Profile.TypeChoices.VOLUNTEER


def filter__learners(user):
    return user.profile.user_type == Profile.TypeChoices.LEARNER


def filter__onboarded_volunteers(user):
    return filter__volunteers(user) and user.state.is_onboarded


def filter__onboarded_learners(user):
    return filter__learners(user) and user.state.is_onboarded


def filter__learners_outside_germany(user):
    if user.state.force_match_eligible:
        return False
    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and (user.profile.country_of_residence != "DE")


def filter__nrw_residents(user):
    dist = pgeocode.GeoDistance("de")
    postal_code_nrw = 51107
    nrw_radius = 150
    distance = dist.query_postal_code(postal_code_nrw, user.profile.postal_code)
    return user.profile.country_of_residence == "DE" and distance < nrw_radius


def filter__random_call_users(user):
    """Same criteria as USER endpoint hasRandomCallsAccess (flag or dev email)."""
    if "herrduenschnlate+" in str(user.email):
        return True
    return user.has_perm(ManagementPermission.USE_RANDOM_CALLS)


def filter__match_eligible_users(user):
    """Onboarded users, excluding learners blocked by A1/A2 rules or outside-Germany learner rules."""
    if not user.state.is_onboarded:
        return False
    if filter__learners_with_a1a2(user):
        return False
    if filter__learners_outside_germany(user):
        return False
    return True


FILTER_FUNC_MAP = {
    AudienceFilters.LEARNERS_WITH_A1A2: filter__learners_with_a1a2,
    AudienceFilters.LEARNERS_ABOVE_A1A2: filter__learners_above_a1a2,
    AudienceFilters.VOLUNTEERS: filter__volunteers,
    AudienceFilters.LEARNERS: filter__learners,
    AudienceFilters.ONBOARDED_VOLUNTEERS: filter__onboarded_volunteers,
    AudienceFilters.ONBOARDED_LEARNERS: filter__onboarded_learners,
    AudienceFilters.LEARNERS_OUTSIDE_GERMANY: filter__learners_outside_germany,
    AudienceFilters.RANDOM_CALL_USERS: filter__random_call_users,
    AudienceFilters.MATCH_ELIGIBLE_USERS: filter__match_eligible_users,
    AudienceFilters.NRW_RESIDENTS: filter__nrw_residents,
}
