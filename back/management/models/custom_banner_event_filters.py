import pgeocode
from django.db import models

from management.models.profile import Profile
from management.models.state import State


class CustomFilterChoices(models.TextChoices):
    CAPEGEMINI = "capegemini", "capegemini"
    LEARNERS_WITH_A1A2 = "learners_with_a1a2", "learners_with_a1a2"
    LEARNERS_ABOVE_A1A2 = "learners_above_a1a2", "learners_above_a1a2"
    VOLUNTEERS = "volunteers", "volunteers"
    LEARNERS = "learners", "learners"
    LEARNERS_OUTSIDE_GERMANY = "learners_outside_germany", "learners_outside_germany"
    RANDOM_CALL_USERS = "random_call_users", "random_call_users"
    MATCH_ELIGIBLE_USERS = "match_eligible_users", "match_eligible_users"
    NRW_RESIDENTS = "nrw_residents", "nrw_residents"
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
    """Same criteria as USER endpoint hasRandomCallAccess (beta flag or dev email)."""
    if "herrduenschnlate+" in str(user.email):
        return True
    return user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.USE_BETA_RANDOM_CALL)


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
    CustomFilterChoices.CAPEGEMINI: filter__learners_above_a1a2,
    CustomFilterChoices.LEARNERS_WITH_A1A2: filter__learners_with_a1a2,
    CustomFilterChoices.LEARNERS_ABOVE_A1A2: filter__learners_above_a1a2,
    CustomFilterChoices.VOLUNTEERS: filter__volunteers,
    CustomFilterChoices.LEARNERS: filter__learners,
    CustomFilterChoices.LEARNERS_OUTSIDE_GERMANY: filter__learners_outside_germany,
    CustomFilterChoices.RANDOM_CALL_USERS: filter__random_call_users,
    CustomFilterChoices.MATCH_ELIGIBLE_USERS: filter__match_eligible_users,
    CustomFilterChoices.NRW_RESIDENTS: filter__nrw_residents,
}
