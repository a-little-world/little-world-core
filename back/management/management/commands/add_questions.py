import json

from django.core.management.base import BaseCommand

from management.models.question_cards import (
    QuestionCard,
    QuestionCardCategory,
    default_translation_content,
)


class Command(BaseCommand):
    help = "Load question card categories and cards from dev_test_data/question_cards.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing question cards and categories before loading.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            QuestionCardCategory.objects.all().delete()
            self.stdout.write("Cleared existing question cards and categories.")
        elif QuestionCardCategory.objects.exists():
            self.stdout.write("Question cards already exist — skipping seed. Use --clear to replace.")
            return

        with open("/back/dev_test_data/question_cards.json", "r") as file:
            data = json.load(file)

        categories = data["categories"]
        card_count = sum(len(category["cards"]) for category in categories)
        self.stdout.write(f"Adding {card_count} cards and {len(categories)} categories")

        for category_index, category in enumerate(categories):
            category_content = category["content"]
            category_model = QuestionCardCategory.objects.create(
                sort_order=category_index,
                content=default_translation_content(
                    en=category_content["en"],
                    de=category_content["de"],
                ),
            )
            self.stdout.write(f"Created category {category_content['en']}")

            for card_index, card in enumerate(category["cards"]):
                QuestionCard.objects.create(
                    category=category_model,
                    sort_order=card_index,
                    content=default_translation_content(en=card["en"], de=card["de"]),
                )

        self.stdout.write(self.style.SUCCESS("Done."))
