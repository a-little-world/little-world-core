from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from video.models import LivekitSession

# Stamp for sessions we have to invent an end for (still open, or already marked unusual
# with a fake 4h/multi-day end). Finished calls with a real hang-up are not recapped,
# even when they lasted longer than this.
UNUSUAL_LENGTH_CUTOFF = timedelta(minutes=45)


def process_unusually_long_sessions(
    cutoff: timedelta | None = None,
    min_age_hours: float | None = None,
    max_age_hours: float | None = None,
    dry_run: bool = False,
    stdout=None,
    cutoff_hours: float | None = None,
):
    """Close stuck LivekitSession rows and stamp them at ``cutoff``.

    A session is stuck when it is still open (``is_active`` / a participant flag / no
    ``end_time``) past ``cutoff``, or already ``unusual_length`` with an end beyond
    ``cutoff`` (the old 4h cap, or a later hang-up that overwrote it).

    Completed calls that closed normally are left alone, including ones longer than
    ``cutoff``. The daily job waits ``min_age_hours`` (24h) so a live call is not
    clipped while people are still in the room.

    On update: ``end_time = created_at + cutoff``, ``unusual_length=True``, and the
    session is deactivated so a later join cannot reuse the row and overwrite the cap.
    """
    if cutoff is None:
        cutoff = timedelta(hours=float(cutoff_hours)) if cutoff_hours is not None else UNUSUAL_LENGTH_CUTOFF

    now = timezone.now()

    age_filters = models.Q()
    if min_age_hours is not None:
        age_filters &= models.Q(created_at__lt=now - timedelta(hours=float(min_age_hours)))
    if max_age_hours is not None:
        age_filters &= models.Q(created_at__gte=now - timedelta(hours=float(max_age_hours)))

    still_open = (
        models.Q(end_time__isnull=True) | models.Q(is_active=True) | models.Q(u1_active=True) | models.Q(u2_active=True)
    )
    stuck_open = LivekitSession.objects.filter(still_open, created_at__lt=now - cutoff)
    if age_filters:
        stuck_open = stuck_open.filter(age_filters)

    unusual_beyond_cutoff = LivekitSession.objects.filter(unusual_length=True).filter(
        models.Q(end_time__isnull=True) | models.Q(end_time__gt=models.F("created_at") + cutoff)
    )
    if age_filters:
        unusual_beyond_cutoff = unusual_beyond_cutoff.filter(age_filters)

    to_fix_ids = list(
        dict.fromkeys(
            [
                *stuck_open.values_list("id", flat=True),
                *unusual_beyond_cutoff.values_list("id", flat=True),
            ]
        )
    )

    if not to_fix_ids:
        if stdout:
            stdout.write("No unusually long sessions found for selection.")
        return {"found": 0, "updated": 0}

    if stdout:
        stdout.write(f"Found {len(to_fix_ids)} session(s) to inspect (cutoff={cutoff})")

    sessions = LivekitSession.objects.filter(id__in=to_fix_ids)

    updated_count = 0
    with transaction.atomic():
        for session in sessions:
            new_end_time = session.created_at + cutoff
            original_end_time = session.end_time.isoformat() if session.end_time else "None"

            already_settled = (
                session.end_time == new_end_time
                and session.unusual_length
                and not session.is_active
                and not session.u1_active
                and not session.u2_active
            )
            if already_settled:
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
                session.is_active = False
                session.u1_active = False
                session.u2_active = False
                session.save(
                    update_fields=[
                        "start_end_before_correction",
                        "unusual_length",
                        "end_time",
                        "is_active",
                        "u1_active",
                        "u2_active",
                    ]
                )
                updated_count += 1

        if dry_run:
            transaction.set_rollback(True)

    return {"found": len(to_fix_ids), "updated": updated_count}
