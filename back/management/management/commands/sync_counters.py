from django.core.management.base import BaseCommand
import json
from management.models.profile import Profile
from management.models.user import User
from management.models.matches import Match
from management.models.question_deck import QuestionCard, QuestionCardCategories, QuestionCardsDeck, _base_translations_dict
from django.db.models import Q


class Command(BaseCommand):
    def handle(self, *args, **options):
        
        print("Re-activating Inactive-Support Matches")
        inactive_support_matches = Match.objects.filter(active=False, support_matching=True)
        c = 0
        total = inactive_support_matches.count()

        # TODO it is titally ok if there are inactive support matches, but the user does always need some support match at-least
        #for match in inactive_support_matches:
        #    c += 1
        #    print(f"Re-activating match {c}/{total}")
        #    match.active = True
        #    match.save()
        
        print("Syncing Match Counters")
        c = 0
        total = Match.objects.all().count()
        
        for match in Match.objects.all():
            c += 1
            print(f"Syncing match {c}/{total}")
            match.sync_counters()
            

        print("Fixing mininum language level of volunteers beeing level-2")
        
        volunteers_impossible_lang_level = User.objects.filter(
            Q(profile__lang_skill__contains=[{
                "lang": Profile.LanguageChoices.GERMAN, 
                "level": Profile.LanguageSkillChoices.LEVEL_0
            }]) | Q(profile__lang_skill__contains=[{
                "lang": Profile.LanguageChoices.GERMAN,
                "level": Profile.LanguageSkillChoices.LEVEL_1
            }]),
            profile__user_type="volunteer"
        )
        
        c = 0
        total = volunteers_impossible_lang_level.count()
        for vol in volunteers_impossible_lang_level:
            c += 1
            print(f"Fixing volunteer {c}/{total}")
            vol.profile.lang_skill = [
                {
                    "lang": Profile.LanguageChoices.GERMAN,
                    "level": Profile.LanguageSkillChoices.LEVEL_2
                }
            ]
            vol.profile.save()