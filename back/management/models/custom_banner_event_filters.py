from django.db import models
from management.models.profile import Profile

class CustomFilterChoices(models.TextChoices):
    CAPEGEMINI = "capegemini", "capegemini"
    LEARNERS_WITH_A1A2 = "learners_with_a1a2", "learners_with_a1a2"
    LEARNERS_ABOVE_A1A2 = "learners_above_a1a2", "learners_above_a1a2"
    VOLUNTEERS = "volunteers", "volunteers"
    LEARNERS = "learners", "learners"
    LEARNERS_OUTSIDE_GERMANY = "learners_outside_germany", "learners_outside_germany"
    NONE = "none", "None"
    
def filter__learners_with_a1a2(user):
    lang_skill_german = list(filter(lambda x: x["lang"] == "german", user.profile.lang_skill))
    german_level = lang_skill_german[0]["level"] if len(lang_skill_german) > 0 else Profile.LanguageSkillChoices.LEVEL_0
    has_a1a2 = german_level == Profile.LanguageSkillChoices.LEVEL_0
    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and has_a1a2

def filter__learners_above_a1a2(user):
    lang_skill_german = list(filter(lambda x: x["lang"] == "german", user.profile.lang_skill))
    german_level = lang_skill_german[0]["level"] if len(lang_skill_german) > 0 else Profile.LanguageSkillChoices.LEVEL_0
    better_than_a1a2 = german_level != Profile.LanguageSkillChoices.LEVEL_0

    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and better_than_a1a2

def filter__volunteers(user):
    return user.profile.user_type == Profile.TypeChoices.VOLUNTEER

def filter__learners(user):
    return user.profile.user_type == Profile.TypeChoices.LEARNER

def filter__learners_outside_germany(user):
    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and (user.profile.residence_country != "DE")

FILTER_FUNC_MAP = {
    CustomFilterChoices.CAPEGEMINI: filter__learners_above_a1a2,
    CustomFilterChoices.LEARNERS_WITH_A1A2: filter__learners_with_a1a2,
    CustomFilterChoices.LEARNERS_ABOVE_A1A2: filter__learners_above_a1a2,
    CustomFilterChoices.VOLUNTEERS: filter__volunteers,
    CustomFilterChoices.LEARNERS: filter__learners,
    CustomFilterChoices.LEARNERS_OUTSIDE_GERMANY: filter__learners_outside_germany,
}