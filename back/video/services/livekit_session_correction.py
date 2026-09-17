from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from video.models import LivekitSession
from video.services.livekit_session_split import drop_session_into, find_nearby_successful_sibling

# Fallback stamp when we invent an end and have no better evidence. Not a detection
# threshold — real calls regularly run longer than this (the longest self-reported is
# ~7 hours).
UNUSUAL_LENGTH_CUTOFF = timedelta(minutes=30)

# How long a session must sit open before we treat it as a clear error rather than a
# real long call. Kept well above the longest call anyone has actually reported.
STUCK_SESSION_DETECTION_CUTOFF = timedelta(hours=10)


def process_unusually_long_sessions(
    *,
    stamp_cutoff: timedelta | None = None,
    detection_cutoff: timedelta | None = None,
    sibling_window: timedelta | None = None,
    min_age_hours: float | None = None,
    max_age_hours: float | None = None,
    dry_run: bool = False,
    stdout=None,
):
    """Resolve stuck LivekitSession rows: drop them into a real sibling if one exists,
    otherwise stamp them at ``stamp_cutoff``.

    A session is stuck when it is still open (``is_active`` / a participant flag / no
    ``end_time``) past ``detection_cutoff``, or already ``unusual_length`` with an end
    beyond ``stamp_cutoff`` (the old 4h cap, or a later hang-up that overwrote it).

    ``detection_cutoff`` only decides when an open session counts as an error — it is
    set far above any real call length so long real conversations are never touched
    while still open. ``stamp_cutoff`` is the invented duration written when a session
    is a genuine error and no sibling explains what really happened.

    For each stuck row, first check for a finished, real mutual call in the same room
    within ``sibling_window`` (default: ``stamp_cutoff``). If one exists, this row is a
    leftover of that real call — its webhook events and FKs move onto the sibling and
    the row is deleted, rather than inventing a stamped duration for a call that is
    already on record elsewhere.

    A positive duration (``created_at + stamp_cutoff``) is only invented when there is
    evidence two people were actually connected at once — ``both_have_been_active`` on
    this row, or that sibling. A row with no sibling and only one participant ever
    active has no such evidence, so it is closed at zero length (``end_time =
    created_at``, ``unusual_length=False``) instead of being stamped as an unusually
    long call it never was.

    Completed calls that closed normally are left alone, including ones longer than
    ``detection_cutoff``. The daily job also waits ``min_age_hours`` (24h) so a live
    call is not touched while people are still in the room.
    """
    stamp_cutoff = stamp_cutoff if stamp_cutoff is not None else UNUSUAL_LENGTH_CUTOFF
    detection_cutoff = detection_cutoff if detection_cutoff is not None else STUCK_SESSION_DETECTION_CUTOFF
    sibling_window = sibling_window if sibling_window is not None else stamp_cutoff

    now = timezone.now()

    age_filters = models.Q()
    if min_age_hours is not None:
        age_filters &= models.Q(created_at__lt=now - timedelta(hours=float(min_age_hours)))
    if max_age_hours is not None:
        age_filters &= models.Q(created_at__gte=now - timedelta(hours=float(max_age_hours)))

    still_open = (
        models.Q(end_time__isnull=True) | models.Q(is_active=True) | models.Q(u1_active=True) | models.Q(u2_active=True)
    )
    stuck_open = LivekitSession.objects.filter(still_open, created_at__lt=now - detection_cutoff)
    if age_filters:
        stuck_open = stuck_open.filter(age_filters)

    unusual_beyond_cutoff = LivekitSession.objects.filter(unusual_length=True).filter(
        models.Q(end_time__isnull=True) | models.Q(end_time__gt=models.F("created_at") + stamp_cutoff)
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
        return {"found": 0, "updated": 0, "dropped": 0, "stamped": 0, "closed_no_show": 0}

    if stdout:
        stdout.write(
            f"Found {len(to_fix_ids)} session(s) to inspect "
            f"(detection_cutoff={detection_cutoff}, stamp_cutoff={stamp_cutoff})"
        )

    sessions = LivekitSession.objects.filter(id__in=to_fix_ids)

    updated_count = 0
    dropped_count = 0
    stamped_count = 0
    closed_no_show_count = 0
    with transaction.atomic():
        for session in sessions:
            sibling = find_nearby_successful_sibling(session, window=sibling_window)
            if sibling is not None:
                if stdout:
                    stdout.write(
                        f"Session {session.uuid} -> dropping into sibling {sibling.uuid} "
                        "(that call is already on record)"
                    )
                if not dry_run:
                    drop_session_into(session, sibling)
                dropped_count += 1
                continue

            # No sibling and never mutual: nobody else was ever connected, so there is
            # no evidence to invent a positive duration from. Close it at zero length
            # instead of stamping a "call" that never had two participants.
            if session.both_have_been_active:
                new_end_time = session.created_at + stamp_cutoff
                new_unusual_length = True
            else:
                new_end_time = session.created_at
                new_unusual_length = False
            original_end_time = session.end_time.isoformat() if session.end_time else "None"

            already_settled = (
                session.end_time == new_end_time
                and session.unusual_length == new_unusual_length
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
                session.unusual_length = new_unusual_length
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
            if new_unusual_length:
                stamped_count += 1
            else:
                closed_no_show_count += 1

        if dry_run:
            transaction.set_rollback(True)

    return {
        "found": len(to_fix_ids),
        "updated": updated_count,
        "dropped": dropped_count,
        "stamped": stamped_count,
        "closed_no_show": closed_no_show_count,
    }
