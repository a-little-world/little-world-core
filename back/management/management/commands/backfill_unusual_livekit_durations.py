"""Restore realistic end times on unusual_length LivekitSession rows.

Dry run unless --apply. Run backfill_split_livekit_sessions first.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from video.services.livekit_session_correction import UNUSUAL_LENGTH_CUTOFF
from video.services.livekit_session_duration_backfill import backfill_unusual_durations


class Command(BaseCommand):
    help = (
        "For unusual_length LivekitSession rows, set end_time from the last participant_left "
        "in the original sitting. With no leave: 45 minutes if this row (or a sibling in "
        "the same room within 45 minutes) is a successful call, clipped to the next session "
        "start if that is sooner; last join (~0s) only when the row is definitely one-sided. "
        "Always deactivates the row. Skips split-pair leftovers. Also recovers any later call "
        "glued onto a row by the old stuck-open reuse bug: events after the first sitting are "
        "split off into their own new session(s), attributed by participant. "
        "Dry run unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the recovered or capped end times. Without this the command only reports.",
        )
        parser.add_argument(
            "--cutoff-minutes",
            type=float,
            default=UNUSUAL_LENGTH_CUTOFF.total_seconds() / 60.0,
            help="Fallback stamp for a successful call with no hang-up (default: 45).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only process the first N unusual rows. Useful for a cautious first pass.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        cutoff = timedelta(minutes=float(options["cutoff_minutes"]))
        limit = options["limit"]

        self.stdout.write(
            "Recovering unusual_length sessions from first-sitting webhooks "
            f"(fallback cap {cutoff.total_seconds() / 60:g} min)."
        )
        result = backfill_unusual_durations(
            apply=apply_changes,
            limit=limit,
            cutoff=cutoff,
            stdout=self.stdout,
        )

        heading = "Result" if apply_changes else "Dry run — nothing written"
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(heading))
        self.stdout.write(f"  unusual rows considered ............ {result['found']}")
        self.stdout.write(f"  skipped (split-pair sessions) ...... {result['skipped_split_sessions']}")
        self.stdout.write(f"  recovered from a hang-up ........... {result['recovered']}")
        self.stdout.write(f"  stamped at 45 min (success, no end)  {result['capped']}")
        self.stdout.write(f"  one-sided last join (~0s) .......... {result['one_sided_join']}")
        self.stdout.write(f"  later sittings recovered as new rows {result['reconstructed_later_sittings']}")
        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f"  updated ............................ {result['updated']}"))
        else:
            self.stdout.write("  Pass --apply to write recovered or 45-minute ends and close the rows.")
