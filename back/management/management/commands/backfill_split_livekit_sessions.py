"""Merge LivekitSession rows that are one successful call split by a join race.

Dry run unless --apply. See video.services.livekit_session_split for the pair definition.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from video.services.livekit_session_split import DEFAULT_MAX_GAP, backfill_split_sessions


class Command(BaseCommand):
    help = (
        "Merge complementary one-sided LivekitSession pairs that are one join-race call: "
        "same room, exactly one 4h-capped leftover, start gap <= 30s. Keeps the real-duration "
        "row, deletes the extra. Dry run unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the merges. Without this the command only reports matching pairs.",
        )
        parser.add_argument(
            "--gap-seconds",
            type=float,
            default=DEFAULT_MAX_GAP.total_seconds(),
            help="Maximum start-time gap to treat two rows as the same call (default: 30).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only merge the first N pairs. Useful for a cautious first pass.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        max_gap = timedelta(seconds=float(options["gap_seconds"]))
        limit = options["limit"]

        self.stdout.write(
            f"Looking for complementary pairs with exactly one 4h-capped row "
            f"and start gap <= {max_gap.total_seconds():g}s."
        )
        result = backfill_split_sessions(
            max_gap=max_gap,
            apply=apply_changes,
            limit=limit,
            stdout=self.stdout,
        )

        heading = "Result" if apply_changes else "Dry run — nothing written"
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(heading))
        self.stdout.write(f"  split pairs found ................... {result['found']}")
        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f"  merged (redundant row dropped) ...... {result['merged']}"))
        else:
            self.stdout.write("  Pass --apply to merge each pair into one session and delete the extra row.")
