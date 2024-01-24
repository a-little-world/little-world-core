from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, **options):
        """
- (1) [o] ( alle Nutzer ) `partner_sex` -> `partner_gender`
- (2) [o] ( alle Nutzer ) `gender -> "Don't want to say"` weil wir vorher nie nach eigenem gender gefragt haben ( koennte auch ne ai/api prediction per NUR vornamen verwenden will aber niemanden offenden )
- (3) [o] ( nur Volunteers ) `lang_level` -> `min_lang_level_partner` da vorher verwendet als "Welches sprach level soll dein partner haben"
- (4) [o] ( nur Volunteers ) `lang_skill["german"]` -> "C1/C2 (complex topics)"` da wir ja voluntters nicht nach ihrem lang level gefragt haben zuvor, gibt jetzt zwar auch Native Speaker, aber denke das hier is besserer default.
- (5) [o] ( nur Lernende ) `lang_level` -> `lang_skill["german"]` da es ja jetzt den multi language level selector gibt
        """
        from management.models.matches import Match
        from management.models.state import State
        from management.models.user import User
        from management.models.profile import Profile
        

        value_map = {
            "patner_gender": {
                Profile.ParterSexChoice.ANY: Profile.PartnerGenderChoices.ANY,
                Profile.ParterSexChoice.MALE: Profile.PartnerGenderChoices.MALE,
                Profile.ParterSexChoice.FEMALE: Profile.PartnerGenderChoices.FEMALE,
            },
            "lang_level": {
                Profile.LanguageLevelChoices.LEVEL_0_LER: Profile.LanguageSkillChoices.LEVEL_0,
                Profile.LanguageLevelChoices.LEVEL_1_LER: Profile.LanguageSkillChoices.LEVEL_1,
                Profile.LanguageLevelChoices.LEVEL_2_LER: Profile.LanguageSkillChoices.LEVEL_2,
                Profile.LanguageLevelChoices.LEVEL_3_LER: Profile.LanguageSkillChoices.LEVEL_3,
                Profile.LanguageLevelChoices.LEVEL_0_VOL: Profile.LanguageSkillChoices.LEVEL_0,
                Profile.LanguageLevelChoices.LEVEL_1_VOL: Profile.LanguageSkillChoices.LEVEL_1,
                Profile.LanguageLevelChoices.LEVEL_2_VOL: Profile.LanguageSkillChoices.LEVEL_2,
                Profile.LanguageLevelChoices.LEVEL_3_VOL: Profile.LanguageSkillChoices.LEVEL_3,
            },
        }
        
        all_profile = Profile.objects.all()
        total = all_profile.count()
        c = 0
        
        for profile in all_profile:
            print(f"Updating Profile: ({c}/{total})")
            profile.partner_gender = value_map["patner_gender"][profile.partner_sex] # (1)
            profile.gender = Profile.GenderChoices.ANY # (2)
            if profile.user_type == Profile.TypeChoices.VOLUNTEER:
                print("Updating Volunteer Profile")
                profile.min_lang_level_partner = value_map["lang_level"][profile.lang_level] # (3)
                profile.lang_skill = [{ "lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_3 }] # (4)
            if profile.user_type == Profile.TypeChoices.LEARNER:
                print("Updating Learner Profile")
                profile.lang_skill = [{ "lang": Profile.LanguageChoices.GERMAN, "level": value_map["lang_level"][profile.lang_level] }] # (5)
            profile.save()
            c += 1