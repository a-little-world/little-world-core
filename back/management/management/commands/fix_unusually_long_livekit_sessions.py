from datetime import timedelta

from django.core.management.base import BaseCommand
from video.services.livekit_session_correction import (
    STUCK_SESSION_DETECTION_CUTOFF,
    UNUSUAL_LENGTH_CUTOFF,
    process_unusually_long_sessions,
)


class Command(BaseCommand):
    help = (
        "Resolve stuck LivekitSession rows (still open, or already unusual with an end "
        "beyond the stamp cutoff). For each: drop it into a real mutual sibling in the same "
        "room if one exists; else, if both users were ever active, mark unusual_length and "
        "stamp end_time to created_at + cutoff (default 30 minutes); else (nobody else ever "
        "joined — no evidence of overlap) close it at zero length instead of inventing a "
        "duration. Stores the previous end in start_end_before_correction if empty. A session "
        "only counts as stuck once it has been open past the detection cutoff (default 10 "
        "hours) — real calls regularly run past 30 minutes and are never touched while still "
        "open. Does not recap finished calls that closed normally."
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
            help="Invented-duration stamp in minutes for a stuck session with no sibling (default: 30).",
        )
        parser.add_argument(
            "--detection-hours",
            type=float,
            default=STUCK_SESSION_DETECTION_CUTOFF.total_seconds() / 3600.0,
            dest="detection_hours",
            help=(
                "How long a session must be open before it counts as a clear error, not a "
                "real long call (default: 10). Keep this well above your longest real calls."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        stamp_cutoff = timedelta(minutes=float(options["cutoff_minutes"]))
        detection_cutoff = timedelta(hours=float(options["detection_hours"]))

        result = process_unusually_long_sessions(
            stamp_cutoff=stamp_cutoff,
            detection_cutoff=detection_cutoff,
            min_age_hours=None,
            max_age_hours=None,
            dry_run=dry_run,
            stdout=self.stdout,
        )

        verb = "would be" if dry_run else "were"
        style = self.style.WARNING if dry_run else self.style.SUCCESS
        self.stdout.write(
            style(
                f"{'Dry-run complete.' if dry_run else 'Done.'} "
                f"{result['stamped']} {verb} stamped at the cutoff (mutual, no better evidence), "
                f"{result['closed_no_show']} {verb} closed at zero length (no-show, no overlap), "
                f"{result['dropped']} {verb} dropped into a sibling."
            )
        )
