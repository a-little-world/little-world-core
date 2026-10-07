from django.core.management.base import BaseCommand
from django.db import transaction

from management.controller import set_user_company
from management.models.user import User

SOURCE_COMPANY = "fh-aachen"
TARGET_COMPANY = "fh-aachen-wi2627"


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
        users = User.objects.filter(state__company=SOURCE_COMPANY).select_related("state").order_by("id")
        count = users.count()

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"DRY RUN: would_change={count}"))
            return

        with transaction.atomic():
            for user in users.iterator():
                set_user_company(user, TARGET_COMPANY)

        self.stdout.write(self.style.SUCCESS(f"DONE: changed={count}"))
