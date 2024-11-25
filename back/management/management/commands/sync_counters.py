from django.core.management.base import BaseCommand
import json
from management.models.user import User
from management.models.matches import Match
from management.models.question_deck import QuestionCard, QuestionCardCategories, QuestionCardsDeck, _base_translations_dict


class Command(BaseCommand):
    def handle(self, *args, **options):
        
        # optimize and sync all counters
        
        c = 0
        total = Match.objects.all().count()
        
        for match in Match.objects.all():
            c += 1
            print(f"Syncing match {c}/{total}")
            match.sync_counters()
        pass