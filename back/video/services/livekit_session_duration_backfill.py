"""Restore realistic end times on ``unusual_length`` LivekitSession rows.

The 4h (now 45min) cap is a placeholder for sessions that never closed. A
``participant_left`` in the original sitting is a real hang-up. With no leave:

- a one-sided row with no successful sibling within 45 minutes is a missed ring
  → last join (~0s)
- a successful call with no hang-up (this row is mutual, or another row in the same
  room within 45 minutes is a finished mutual call) → 45 minutes, clipped to the next
  session in this room if that starts sooner (same pair cannot overlap)

``start_end_before_correction`` is an audit of the cap job, not a hang-up.

Run ``backfill_split_livekit_sessions`` first. Split leftovers are skipped so this
command cannot clear ``unusual_length`` on a row the merge still needs.
"""

from datetime import timedelta

from django.db import transaction
from video.models import LivekitSession
from video.services.livekit_session_correction import UNUSUAL_LENGTH_CUTOFF
from video.services.livekit_session_split import find_split_pairs

# How far after ``created_at`` an event still belongs to the original sitting. The old
# daily job stamped 4h, so a next-week join/leave that overwrote the cap is outside this
# and must not become the recovered end. This is not the 45-minute fallback stamp.
FIRST_CALL_EVENT_WINDOW = timedelta(hours=4)


def _events_in_first_sitting(session, window: timedelta = FIRST_CALL_EVENT_WINDOW):
    cutoff_at = session.created_at + window
    return [event for event in session.webhook_events.all() if event.created_at <= cutoff_at]


def recovered_leave_end(session, window: timedelta = FIRST_CALL_EVENT_WINDOW):
    """Last hang-up from the original sitting, or None."""
    leaves = [
        event for event in _events_in_first_sitting(session, window) if event.data.get("event") == "participant_left"
    ]
    if not leaves:
        return None
    recovered = max(event.created_at for event in leaves)
    if recovered < session.created_at:
        return session.created_at
    return recovered


def last_event_end(session, window: timedelta = FIRST_CALL_EVENT_WINDOW):
    """Last webhook in the original sitting (usually a join), or None."""
    events = _events_in_first_sitting(session, window)
    if not events:
        return None
    recovered = max(event.created_at for event in events)
    if recovered < session.created_at:
        return session.created_at
    return recovered


def _nearby_successful_sibling(session, window: timedelta) -> bool:
    """Another row in this room is a finished mutual call inside ``window``."""
    if session.room_id is None or session.created_at is None:
        return False
    return (
        LivekitSession.objects.filter(
            room_id=session.room_id,
            both_have_been_active=True,
            unusual_length=False,
            end_time__isnull=False,
            created_at__gte=session.created_at - window,
            created_at__lte=session.created_at + window,
        )
        .exclude(pk=session.pk)
        .exists()
    )


def _next_session_start(session):
    """When the next LivekitSession in this room begins, if any."""
    if session.room_id is None or session.created_at is None:
        return None
    return (
        LivekitSession.objects.filter(room_id=session.room_id, created_at__gt=session.created_at)
        .exclude(pk=session.pk)
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )


def _capped_end(session, cutoff: timedelta):
    """``created_at + cutoff``, or the next same-room start if that is sooner.

    A later call in this room means this sitting had already ended. Stamping a full
    45 minutes would overlap that row. Duration is min(cutoff, next_start - created_at).
    """
    cap = session.created_at + cutoff
    nxt = _next_session_start(session)
    if nxt is not None and session.created_at < nxt < cap:
        return nxt
    return cap


def choose_unusual_end(session, cutoff: timedelta = UNUSUAL_LENGTH_CUTOFF) -> tuple:
    """Return (end_time, unusual_length, source) for one unusual row."""
    leave_end = recovered_leave_end(session)
    if leave_end is not None:
        return leave_end, False, "leave"

    if session.both_have_been_active or _nearby_successful_sibling(session, window=cutoff):
        return _capped_end(session, cutoff), True, "cutoff"

    join_end = last_event_end(session)
    if join_end is not None:
        return join_end, False, "one_sided_join"

    return _capped_end(session, cutoff), True, "cutoff"


def _split_pair_ids() -> set[int]:
    ids: set[int] = set()
    for first, second in find_split_pairs():
        ids.add(first.pk)
        ids.add(second.pk)
    return ids


def _apply_duration(session, new_end, *, unusual: bool) -> None:
    session.end_time = new_end
    session.unusual_length = unusual
    session.is_active = False
    session.u1_active = False
    session.u2_active = False
    session.save(update_fields=["end_time", "unusual_length", "is_active", "u1_active", "u2_active"])


def backfill_unusual_durations(
    *,
    apply: bool = False,
    limit: int | None = None,
    cutoff: timedelta = UNUSUAL_LENGTH_CUTOFF,
    stdout=None,
) -> dict:
    skip_ids = _split_pair_ids()
    sessions = list(
        LivekitSession.objects.filter(unusual_length=True)
        .exclude(pk__in=skip_ids)
        .prefetch_related("webhook_events")
        .order_by("pk")
    )
    if limit is not None:
        sessions = sessions[:limit]

    counts = {"leave": 0, "cutoff": 0, "one_sided_join": 0}
    updated = 0

    for session in sessions:
        new_end, unusual, source = choose_unusual_end(session, cutoff=cutoff)

        already_settled = (
            session.end_time == new_end
            and session.unusual_length == unusual
            and not session.is_active
            and not session.u1_active
            and not session.u2_active
        )
        if stdout:
            stdout.write(
                f"  session {session.pk}  {source}  "
                f"end {session.end_time} -> {new_end}  unusual {session.unusual_length} -> {unusual}"
            )
        if already_settled:
            continue
        if apply:
            with transaction.atomic():
                _apply_duration(session, new_end, unusual=unusual)
            updated += 1
        counts[source] = counts.get(source, 0) + 1

    return {
        "found": len(sessions),
        "skipped_split_sessions": len(skip_ids),
        "recovered": counts["leave"],
        "capped": counts["cutoff"],
        "one_sided_join": counts["one_sided_join"],
        "updated": updated,
    }
