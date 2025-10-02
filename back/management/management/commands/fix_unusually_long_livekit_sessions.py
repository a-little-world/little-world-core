from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from video.services.livekit_session_correction import process_unusually_long_sessions


class Command(BaseCommand):
    help = (
        "Scan LivekitSession rows longer than 4 hours, mark as unusual, "
        "store original start/end in start_end_before_correction, and cap end_time to start + 4h."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Only report what would change without writing to the database.",
        )
        parser.add_argument(
            "--cutoff-hours",
            type=float,
            default=4.0,
            dest="cutoff_hours",
            help="Cutoff duration in hours (default: 4). Sessions longer than this are capped.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        cutoff_hours = float(options.get("cutoff_hours", 4.0))

        result = process_unusually_long_sessions(
            cutoff_hours=cutoff_hours,
            min_age_hours=None,
            max_age_hours=None,
            dry_run=dry_run,
            stdout=self.stdout,
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run complete. {result['found']} session(s) would be updated."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Updated {result['updated']} unusually long session(s).")
            )


