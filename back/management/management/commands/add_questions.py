import json

from django.core.management.base import BaseCommand

from management.models.question_deck import (
    QuestionCard,
    QuestionCardCategories,
    QuestionCardsDeck,
    _base_translations_dict,
)
from management.models.user import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        with open("/back/dev_test_data/question_cards.json", "r") as file:
            data = json.load(file)

        cards = data["cards"]
        categories = data["categories"]

        print(f"Adding {len(cards)} cards and {len(categories)} categories")

        # 1 - create all categories
        for category in categories:
            category_model = QuestionCardCategories.objects.filter(ref_id=int(category["id"]))
            if not category_model.exists():
                print("creating category")
                category_model = QuestionCardCategories.objects.create(
                    ref_id=int(category["id"]), content=_base_translations_dict(en=category["en"], de=category["de"])
                )

        # 2 - create all cards
        for card in cards:
            card_model = QuestionCard.objects.filter(ref_id=int(card["id"]))
            if not card_model.exists():
                print("creating card")
                category = QuestionCardCategories.objects.filter(ref_id=int(card["category"])).first()
                card_model = QuestionCard.objects.create(
                    ref_id=int(card["id"]),
                    category=category,
                    content=_base_translations_dict(en=card["en"], de=card["de"]),
                )

        # 3 - create a deck for all users ( that don't yet have one )
        if False:
            # Just needed in migration
            for user in User.objects.all():
                print(f"checking user {user.email}")
                try:
                    if not user.state.question_card_deck:
                        question_card_deck = QuestionCardsDeck.objects.create(user=user)
                        question_card_deck.cards.set(QuestionCard.objects.all())
                        question_card_deck.save()
                        user.state.question_card_deck = question_card_deck
                        user.state.save()
                    elif user.state.question_card_deck.cards.count() == 0:
                        question_card_deck = user.state.question_card_deck
                        question_card_deck.cards.set(QuestionCard.objects.all())
                        question_card_deck.save()
                except:
                    print(f"error with user {user.email}")
