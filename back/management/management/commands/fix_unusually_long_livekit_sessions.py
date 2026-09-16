from datetime import timedelta

from django.core.management.base import BaseCommand
from video.services.livekit_session_correction import UNUSUAL_LENGTH_CUTOFF, process_unusually_long_sessions


class Command(BaseCommand):
    help = (
        "Close stuck LivekitSession rows (still open, or already unusual with an end beyond "
        "the cutoff), mark unusual_length, store the previous end in start_end_before_correction "
        "if empty, and stamp end_time to created_at + cutoff (default 45 minutes). "
        "Does not recap finished calls that closed normally."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Only report what would change without writing to the database.",
        )
        parser.add_argument(
            "--cutoff-minutes",
            type=float,
            default=UNUSUAL_LENGTH_CUTOFF.total_seconds() / 60.0,
            dest="cutoff_minutes",
            help="Cutoff duration in minutes (default: 45). Stuck sessions are stamped to this.",
        )
        parser.add_argument(
            "--cutoff-hours",
            type=float,
            default=None,
            dest="cutoff_hours",
            help="Override cutoff in hours. If set, takes precedence over --cutoff-minutes.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        if options.get("cutoff_hours") is not None:
            cutoff = timedelta(hours=float(options["cutoff_hours"]))
        else:
            cutoff = timedelta(minutes=float(options["cutoff_minutes"]))

        result = process_unusually_long_sessions(
            cutoff=cutoff,
            min_age_hours=None,
            max_age_hours=None,
            dry_run=dry_run,
            stdout=self.stdout,
        )

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry-run complete. {result['found']} session(s) would be updated."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated {result['updated']} unusually long session(s)."))
