from django.core.management.base import BaseCommand
from django.db import transaction

from management.models.state import State

SOURCE_COMPANY = "fh-aachen"
TARGET_COMPANY = "fh-aachen-Wi2627"


class Command(BaseCommand):
    help = (
        f'Change users assigned to "{SOURCE_COMPANY}" to "{TARGET_COMPANY}". '
        "The previous company is retained in state.past_companies."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many users would be changed without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        states = State.objects.filter(company=SOURCE_COMPANY).order_by("id")
        count = states.count()

        if not dry_run:
            with transaction.atomic():
                for state in states.iterator():
                    state.past_companies = [*state.past_companies, SOURCE_COMPANY]
                    state.company = TARGET_COMPANY
                    state.save(update_fields=["company", "past_companies", "updated_at"])

        mode = "DRY RUN" if dry_run else "DONE"
        self.stdout.write(self.style.SUCCESS(f"{mode}: changed={count}"))
