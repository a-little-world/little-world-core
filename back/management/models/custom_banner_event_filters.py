from django.db import models
class CustomFilterChoices(models.TextChoices):
    CAPEGEMINI = "capegemini", "capegemini"
    NONE = "none", "None"

def filter__capegemini(user):

    from management.models.profile import Profile
    lang_skill_german = list(filter(lambda x: x["lang"] == "german", user.profile.lang_skill))
    german_level = lang_skill_german[0]["level"] if len(lang_skill_german) > 0 else Profile.LanguageSkillChoices.LEVEL_0
    better_than_a1a2 = german_level != Profile.LanguageSkillChoices.LEVEL_0

    return (user.profile.user_type == Profile.TypeChoices.LEARNER) and better_than_a1a2


FILTER_FUNC_MAP = {
    CustomFilterChoices.CAPEGEMINI: filter__capegemini,
}