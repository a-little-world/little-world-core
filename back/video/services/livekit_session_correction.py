from datetime import timedelta

from django.db import transaction, models
from django.utils import timezone

from video.models import LivekitSession


def process_unusually_long_sessions(
    cutoff_hours: float = 4.0,
    min_age_hours: float | None = None,
    max_age_hours: float | None = None,
    dry_run: bool = False,
    stdout=None,
):
    """
    Correct LivekitSession rows longer than cutoff.

    - If end_time is set and beyond created_at + cutoff -> cap it and mark unusual_length
    - If end_time is null and session age > cutoff -> set end_time to created_at + cutoff and mark unusual_length
    - Re-apply for sessions already marked unusual_length to adjust to new cutoff

    Optionally limit to sessions whose age is within [min_age_hours, max_age_hours).

    Returns: {"found": int, "updated": int}
    """
    now = timezone.now()
    cutoff_delta = timedelta(hours=float(cutoff_hours))

    age_filters = models.Q()
    if min_age_hours is not None:
        age_filters &= models.Q(created_at__lt=now - timedelta(hours=float(min_age_hours)))
    if max_age_hours is not None:
        age_filters &= models.Q(created_at__gte=now - timedelta(hours=float(max_age_hours)))

    sessions_with_end_too_long = LivekitSession.objects.filter(
        end_time__isnull=False,
        end_time__gt=models.F("created_at") + cutoff_delta,
    )
    if age_filters:
        sessions_with_end_too_long = sessions_with_end_too_long.filter(age_filters)

    sessions_without_end_too_long = LivekitSession.objects.filter(
        end_time__isnull=True,
        created_at__lt=now - cutoff_delta,
    )
    if age_filters:
        sessions_without_end_too_long = sessions_without_end_too_long.filter(age_filters)

    previously_marked = LivekitSession.objects.filter(
        unusual_length=True,
    )
    if age_filters:
        previously_marked = previously_marked.filter(age_filters)
    previously_marked = previously_marked.exclude(
        id__in=models.Subquery(
            LivekitSession.objects.filter(
                end_time__isnull=False,
                end_time__lte=models.F("created_at") + cutoff_delta,
            ).values("id")
        )
    )

    to_fix_ids = list(sessions_with_end_too_long.values_list("id", flat=True)) + list(
        sessions_without_end_too_long.values_list("id", flat=True)
    ) + list(previously_marked.values_list("id", flat=True))

    if not to_fix_ids:
        if stdout:
            stdout.write("No unusually long sessions found for selection.")
        return {"found": 0, "updated": 0}

    if stdout:
        stdout.write(f"Found {len(to_fix_ids)} session(s) to inspect (cutoff={cutoff_hours}h)")

    sessions = LivekitSession.objects.filter(id__in=to_fix_ids)

    updated_count = 0
    with transaction.atomic():
        for session in sessions:
            new_end_time = session.created_at + cutoff_delta

            original_end_time = session.end_time.isoformat() if session.end_time else "None"

            if session.end_time == new_end_time and session.unusual_length:
                continue

            if stdout:
                stdout.write(
                    f"Session {session.uuid} -> setting end_time to {new_end_time.isoformat()} (was {original_end_time})"
                )

            if not dry_run:
                if not session.start_end_before_correction:
                    session.start_end_before_correction = (
                        f"created_at={session.created_at.isoformat() if session.created_at else 'None'}; "
                        f"end_time={original_end_time}"
                    )
                session.unusual_length = True
                session.end_time = new_end_time
                session.save(update_fields=[
                    "start_end_before_correction",
                    "unusual_length",
                    "end_time",
                ])
                updated_count += 1

        if dry_run:
            transaction.set_rollback(True)

    return {"found": len(to_fix_ids), "updated": updated_count}


