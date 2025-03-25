from django.db import models
from management.models.profile import Profile

class CustomFilterChoices(models.TextChoices):
    CAPEGEMINI = "capegemini", "capegemini"
    LEARNERS_ABOVE_A1A2 = "learners_above_a1a2", "learners_above_a1a2"
    VOLUNTEERS = "volunteers", "volunteers"
    LEARNERS = "learners", "learners"
    NONE = "none", "None"

def filter__learners_above_a1a2(user):

    lang_skill_german = list(filter(lambda x: x["lang"] == "german", user.profile.lang_skill))
    german_level = lang_skill_german[0]["level"] if len(lang_skill_german) > 0 else Profile.LanguageSkillChoices.LEVEL_0
    better_than_a1a2 = german_level != Profile.LanguageSkillChoices.LEVEL_0

    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and better_than_a1a2

def filter__volunteers(user):
    return user.profile.user_type == Profile.TypeChoices.VOLUNTEER

def filter__learners(user):
    return user.profile.user_type == Profile.TypeChoices.LEARNER


FILTER_FUNC_MAP = {
    CustomFilterChoices.CAPEGEMINI: filter__learners_above_a1a2,
    CustomFilterChoices.LEARNERS_ABOVE_A1A2: filter__learners_above_a1a2,
    CustomFilterChoices.VOLUNTEERS: filter__volunteers,
    CustomFilterChoices.LEARNERS: filter__learners,
}