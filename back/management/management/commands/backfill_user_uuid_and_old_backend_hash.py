import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from management.models.user import User


class Command(BaseCommand):
    help = "Backfill user.uuid and old_backend_user_hash without modifying legacy hash."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of users to process per batch.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview how many users would be changed without writing.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        queryset = User.objects.all().only("id", "uuid", "hash", "old_backend_user_hash").order_by("id")
        total = queryset.count()
        changed = 0
        processed = 0

        buffer = []
        for user in queryset.iterator(chunk_size=batch_size):
            processed += 1
            update_needed = False

            if not user.uuid:
                user.uuid = uuid.uuid4()
                update_needed = True

            if not user.old_backend_user_hash and user.hash:
                user.old_backend_user_hash = user.hash
                update_needed = True

            if update_needed:
                changed += 1
                if not dry_run:
                    buffer.append(user)

            if len(buffer) >= batch_size:
                self._flush(buffer)
                buffer.clear()

            if processed % batch_size == 0:
                self.stdout.write(f"Processed {processed}/{total} users")

        if buffer and not dry_run:
            self._flush(buffer)

        mode = "DRY RUN" if dry_run else "DONE"
        self.stdout.write(self.style.SUCCESS(f"{mode}: processed={processed}, changed={changed}"))

    @staticmethod
    def _flush(users):
        with transaction.atomic():
            User.objects.bulk_update(users, ["uuid", "old_backend_user_hash"], batch_size=len(users))
