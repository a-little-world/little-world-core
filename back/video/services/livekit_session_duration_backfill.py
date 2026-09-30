"""Restore realistic end times on ``unusual_length`` LivekitSession rows, and recover any
later call glued onto one by the stuck-open reuse bug (fixed at the source: joins now
lock the room and a later join can no longer attach to a row that never closed).

The 4h (now 30min) cap is a placeholder for sessions that never closed. A
``participant_left`` in the original sitting is a real hang-up. With no leave:

- a one-sided row with no successful sibling within 30 minutes is a missed ring
  → last join (~0s)
- a successful call with no hang-up (this row is mutual, or another row in the same
  room within 30 minutes is a finished mutual call) → 30 minutes, clipped to the next
  session in this room if that starts sooner (same pair cannot overlap)

``start_end_before_correction`` is an audit of the cap job, not a hang-up.

A row that was reused before the join-lock fix can carry webhook events from more than
one real call — a next-week join/leave stamped over the same row. Any of this session's
events that fall after the first sitting are grouped into their own later sittings and
materialized as separate LivekitSession rows (moving those events off this row), instead
of being silently ignored.

Run ``backfill_split_livekit_sessions`` first. Split leftovers are skipped so this
command cannot clear ``unusual_length`` on a row the merge still needs.
"""

from datetime import timedelta

from django.db import transaction
from video.models import LivekitSession
from video.services.livekit_session_correction import UNUSUAL_LENGTH_CUTOFF
from video.services.livekit_session_split import find_nearby_successful_sibling, find_split_pairs

# How far after ``created_at`` an event still belongs to the original sitting. The old
# daily job stamped 4h, so a next-week join/leave that overwrote the cap is outside this
# and must not become the recovered end. This is not the 30-minute fallback stamp. Also
# used as the maximum gap between events within one later, reconstructed sitting.
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


def _next_session_start(room_id, after, *, exclude_pk=None):
    """When the next LivekitSession in this room begins after ``after``, if any."""
    if room_id is None or after is None:
        return None
    qs = LivekitSession.objects.filter(room_id=room_id, created_at__gt=after)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.order_by("created_at").values_list("created_at", flat=True).first()


def _capped_end(*, room_id, created_at, cutoff: timedelta, exclude_pk=None):
    """``created_at + cutoff``, or the next same-room start if that is sooner.

    A later call in this room means this sitting had already ended. Stamping a full
    cutoff would overlap that row. Duration is min(cutoff, next_start - created_at).
    """
    cap = created_at + cutoff
    nxt = _next_session_start(room_id, created_at, exclude_pk=exclude_pk)
    if nxt is not None and created_at < nxt < cap:
        return nxt
    return cap


def choose_unusual_end(session, cutoff: timedelta = UNUSUAL_LENGTH_CUTOFF) -> tuple:
    """Return (end_time, unusual_length, source) for one unusual row."""
    leave_end = recovered_leave_end(session)
    if leave_end is not None:
        return leave_end, False, "leave"

    has_sibling = find_nearby_successful_sibling(session, window=cutoff) is not None
    if session.both_have_been_active or has_sibling:
        end = _capped_end(room_id=session.room_id, created_at=session.created_at, cutoff=cutoff, exclude_pk=session.pk)
        return end, True, "cutoff"

    join_end = last_event_end(session)
    if join_end is not None:
        return join_end, False, "one_sided_join"

    end = _capped_end(room_id=session.room_id, created_at=session.created_at, cutoff=cutoff, exclude_pk=session.pk)
    return end, True, "cutoff"


def _event_side(session, event):
    """Which participant (``"u1"``/``"u2"``) a webhook belongs to, or None if it can't
    be matched to either of this session's two participants."""
    identity = (event.data or {}).get("participant", {}).get("identity")
    if not identity:
        return None
    if identity == str(session.u1.uuid):
        return "u1"
    if identity == str(session.u2.uuid):
        return "u2"
    return None


def later_sitting_clusters(session, window: timedelta = FIRST_CALL_EVENT_WINDOW) -> list[list]:
    """Group this session's webhook events that fall after the first sitting into
    separate later sittings — real calls a stuck-open row absorbed by being reused
    while ``is_active`` stayed True.
    """
    first_cutoff = session.created_at + FIRST_CALL_EVENT_WINDOW
    later = sorted(
        (event for event in session.webhook_events.all() if event.created_at > first_cutoff),
        key=lambda event: event.created_at,
    )
    clusters: list[list] = []
    for event in later:
        if clusters and (event.created_at - clusters[-1][-1].created_at) <= window:
            clusters[-1].append(event)
        else:
            clusters.append([event])
    return clusters


def _cluster_session_kwargs(session, cluster: list, cutoff: timedelta):
    """Turn one later-sitting event cluster into LivekitSession field values plus the
    events it covers, or None if those events can't all be attributed to this room's
    two participants (we do not invent a session from data we can't read).
    """
    sides: dict[str, list] = {}
    for event in cluster:
        side = _event_side(session, event)
        if side is None:
            return None
        sides.setdefault(side, []).append(event)

    start = min(event.created_at for event in cluster)
    leaves = [event for event in cluster if event.data.get("event") == "participant_left"]
    both_active = "u1" in sides and "u2" in sides

    if leaves:
        end = max(event.created_at for event in leaves)
        unusual = False
    elif both_active:
        end = _capped_end(room_id=session.room_id, created_at=start, cutoff=cutoff, exclude_pk=session.pk)
        unusual = True
    else:
        end = max(event.created_at for event in cluster)
        unusual = False

    first_side = min(sides, key=lambda side: sides[side][0].created_at)

    kwargs = {
        "room_id": session.room_id,
        "u1_id": session.u1_id,
        "u2_id": session.u2_id,
        "created_at": start,
        "end_time": end,
        "is_active": False,
        "u1_active": False,
        "u2_active": False,
        "u1_was_active": "u1" in sides,
        "u2_was_active": "u2" in sides,
        "both_have_been_active": both_active,
        "unusual_length": unusual,
        "first_active_user_id": session.u1_id if first_side == "u1" else session.u2_id,
        "random_call_session": session.random_call_session,
    }
    return kwargs, cluster


def reconstruct_later_sittings(
    session, *, cutoff: timedelta = UNUSUAL_LENGTH_CUTOFF, apply: bool = False, stdout=None
) -> int:
    """Materialize each later call glued onto ``session`` as its own LivekitSession,
    moving its webhook events off ``session`` onto the new row.

    Returns how many later sittings were found, whether or not ``apply`` writes them.
    """
    found = 0
    for cluster in later_sitting_clusters(session):
        built = _cluster_session_kwargs(session, cluster, cutoff)
        if built is None:
            continue
        kwargs, events = built
        found += 1
        if stdout:
            stdout.write(
                f"  session {session.pk}: later sitting {kwargs['created_at']} -> {kwargs['end_time']} "
                f"(mutual={kwargs['both_have_been_active']}) recovered as a new session"
            )
        if apply:
            with transaction.atomic():
                new_session = LivekitSession.create_backdated(**kwargs)
                session.webhook_events.remove(*events)
                new_session.webhook_events.add(*events)
    return found


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
        .select_related("u1", "u2")
        .prefetch_related("webhook_events")
        .order_by("pk")
    )
    if limit is not None:
        sessions = sessions[:limit]

    counts = {"leave": 0, "cutoff": 0, "one_sided_join": 0}
    updated = 0
    reconstructed = 0

    for session in sessions:
        reconstructed += reconstruct_later_sittings(session, cutoff=cutoff, apply=apply, stdout=stdout)

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
        "reconstructed_later_sittings": reconstructed,
        "updated": updated,
    }
