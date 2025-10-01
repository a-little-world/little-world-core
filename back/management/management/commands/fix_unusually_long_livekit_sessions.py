from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.utils import timezone

from video.models import LivekitSession


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

        now = timezone.now()
        cutoff_hours = float(options.get("cutoff_hours", 4.0))
        cutoff_delta = timedelta(hours=cutoff_hours)

        # Sessions where end_time exists and exceeds 4h duration
        sessions_with_end_too_long = LivekitSession.objects.filter(
            end_time__isnull=False,
            end_time__gt=models.F("created_at") + cutoff_delta,
        )

        # Sessions without end_time that have been open for > 4h (treat as too long)
        sessions_without_end_too_long = LivekitSession.objects.filter(
            end_time__isnull=True,
            created_at__lt=now - cutoff_delta,
        )

        # Sessions previously marked unusual should be re-evaluated with the new cutoff
        previously_marked = LivekitSession.objects.filter(
            unusual_length=True,
        ).exclude(id__in=models.Subquery(
            LivekitSession.objects.filter(
                end_time__isnull=False,
                end_time__lte=models.F("created_at") + cutoff_delta,
            ).values("id")
        ))

        to_fix_ids = list(sessions_with_end_too_long.values_list("id", flat=True)) + list(
            sessions_without_end_too_long.values_list("id", flat=True)
        ) + list(previously_marked.values_list("id", flat=True))

        if not to_fix_ids:
            self.stdout.write(self.style.SUCCESS("No unusually long sessions found."))
            return

        self.stdout.write(
            f"Found {len(to_fix_ids)} unusually long session(s) to inspect. Dry-run={dry_run}"
        )

        sessions = LivekitSession.objects.filter(id__in=to_fix_ids).select_related("u1", "u2", "room")

        updated_count = 0
        with transaction.atomic():
            for session in sessions:
                new_end_time = session.created_at + cutoff_delta

                original_created_at = session.created_at.isoformat() if session.created_at else "None"
                original_end_time = session.end_time.isoformat() if session.end_time else "None"

                # If already capped correctly for this cutoff, skip
                if session.end_time == new_end_time and session.unusual_length:
                    continue

                before_txt = (
                    f"created_at={original_created_at}; end_time={original_end_time}"
                )

                self.stdout.write(
                    f"Session {session.uuid} -> setting end_time to {new_end_time.isoformat()} (was {original_end_time})"
                )

                if not dry_run:
                    # Preserve original record if already present, otherwise store it
                    if not session.start_end_before_correction:
                        session.start_end_before_correction = before_txt
                    session.unusual_length = True
                    session.end_time = new_end_time
                    session.save(update_fields=[
                        "start_end_before_correction",
                        "unusual_length",
                        "end_time",
                    ])
                    updated_count += 1

            if dry_run:
                # In dry-run, do not persist any changes
                transaction.set_rollback(True)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run complete. {len(to_fix_ids)} session(s) would be updated."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Updated {updated_count} unusually long session(s).")
            )


