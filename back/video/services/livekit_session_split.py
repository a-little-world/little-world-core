"""Merge LivekitSession pairs that are one call split by a concurrent-join race.

Two `participant_joined` webhooks can each create a one-sided row for the same room.
Together they are a successful call (`both_have_been_active` would have been true on a
single row); separately they are counted as inactive. Typical shape: complementary
`was_active` flags, exactly one row 4h-capped (`unusual_length`) because it never got a
leave, the other holding the real duration, starts within 30 seconds.

A wider gap without the leftover signature would merge sequential missed calls (one person
rang and hung up, then the other rang). Overlap against the 4h end would merge later
unrelated rings that sit inside that fake window.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from video.models import LivekitSession

DEFAULT_MAX_GAP = timedelta(seconds=30)


def _one_sided_u1(session) -> bool:
    was_u1 = session.u1_was_active or session.u1_active
    was_u2 = session.u2_was_active or session.u2_active
    return was_u1 and not was_u2


def _one_sided_u2(session) -> bool:
    was_u1 = session.u1_was_active or session.u1_active
    was_u2 = session.u2_was_active or session.u2_active
    return was_u2 and not was_u1


def _is_complementary(a: LivekitSession, b: LivekitSession) -> bool:
    return (_one_sided_u1(a) and _one_sided_u2(b)) or (_one_sided_u2(a) and _one_sided_u1(b))


def _exactly_one_unusual(a: LivekitSession, b: LivekitSession) -> bool:
    return a.unusual_length != b.unusual_length


def _event_count(session) -> int:
    annotated = getattr(session, "_event_count", None)
    if annotated is not None:
        return annotated
    return session.webhook_events.count()


def choose_keeper(a: LivekitSession, b: LivekitSession) -> tuple[LivekitSession, LivekitSession]:
    """Keep the real-duration row; drop the 4h-capped leftover when that signature is present."""
    if a.unusual_length != b.unusual_length:
        return (b, a) if a.unusual_length else (a, b)
    a_n, b_n = _event_count(a), _event_count(b)
    if a_n != b_n:
        return (a, b) if a_n > b_n else (b, a)
    if a.pk <= b.pk:
        return a, b
    return b, a


def _real_end_time(a: LivekitSession, b: LivekitSession):
    if a.unusual_length and not b.unusual_length:
        return b.end_time
    if b.unusual_length and not a.unusual_length:
        return a.end_time
    ends = [session.end_time for session in (a, b) if session.end_time is not None]
    return max(ends) if ends else None


def find_split_pairs(*, max_gap: timedelta = DEFAULT_MAX_GAP) -> list[tuple[LivekitSession, LivekitSession]]:
    sessions = list(
        LivekitSession.objects.filter(both_have_been_active=False, room_id__isnull=False)
        .annotate(_event_count=Count("webhook_events"))
        .order_by("room_id", "created_at", "pk")
    )
    pairs: list[tuple[LivekitSession, LivekitSession]] = []
    used: set[int] = set()

    by_room: dict[int, list[LivekitSession]] = {}
    for session in sessions:
        by_room.setdefault(session.room_id, []).append(session)

    for room_sessions in by_room.values():
        for i, first in enumerate(room_sessions):
            if first.pk in used:
                continue
            for second in room_sessions[i + 1 :]:
                if second.pk in used:
                    continue
                gap = second.created_at - first.created_at
                if gap > max_gap:
                    break
                if not _is_complementary(first, second):
                    continue
                if not _exactly_one_unusual(first, second):
                    continue
                pairs.append((first, second))
                used.add(first.pk)
                used.add(second.pk)
                break
    return pairs


def _retarget_survey_responses(drop: LivekitSession, keeper: LivekitSession) -> None:
    from management.models.survey import SurveyResponse

    old_token = f"live_session:{drop.uuid}"
    new_token = f"live_session:{keeper.uuid}"
    for response in SurveyResponse.objects.filter(Q(live_session=drop) | Q(context_key__contains=old_token)):
        new_key = response.context_key.replace(old_token, new_token)
        duplicate = (
            SurveyResponse.objects.filter(
                campaign_id=response.campaign_id,
                user_id=response.user_id,
                context_key=new_key,
            )
            .exclude(pk=response.pk)
            .exists()
        )
        if duplicate:
            response.delete()
            continue
        try:
            SurveyResponse.objects.filter(pk=response.pk).update(live_session=keeper, context_key=new_key)
        except IntegrityError:
            response.delete()


def _retarget_other_live_session_fks(drop: LivekitSession, keeper: LivekitSession) -> None:
    handled = {"survey_responses", "webhook_events"}
    for rel in LivekitSession._meta.related_objects:
        accessor = rel.get_accessor_name()
        if accessor in handled or rel.many_to_many:
            continue
        if not rel.one_to_many or rel.field.name != "live_session":
            continue
        rel.related_model.objects.filter(live_session=drop).update(live_session=keeper)


def drop_session_into(drop: LivekitSession, keeper: LivekitSession) -> None:
    """Move ``drop``'s webhook events and other FKs onto ``keeper``, then delete ``drop``.

    ``keeper``'s own fields are left untouched — use this when ``keeper`` already
    correctly represents the real call and ``drop`` is a pure duplicate/leftover.
    """
    with transaction.atomic():
        _retarget_survey_responses(drop, keeper)
        _retarget_other_live_session_fks(drop, keeper)
        keeper.webhook_events.add(*drop.webhook_events.all())
        drop.delete()


def find_nearby_successful_sibling(session: LivekitSession, window: timedelta) -> LivekitSession | None:
    """The closest finished, real (non-invented) mutual call in this room within ``window``."""
    if session.room_id is None or session.created_at is None:
        return None
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
        .order_by("created_at")
        .first()
    )


def merge_split_session_pair(a: LivekitSession, b: LivekitSession) -> LivekitSession:
    keeper, drop = choose_keeper(a, b)
    earlier = a if a.created_at <= b.created_at else b
    real_end = _real_end_time(a, b)

    with transaction.atomic():
        drop_session_into(drop, keeper)
        LivekitSession.objects.filter(pk=keeper.pk).update(
            created_at=earlier.created_at,
            end_time=real_end,
            u1_was_active=True,
            u2_was_active=True,
            both_have_been_active=True,
            u1_active=False,
            u2_active=False,
            is_active=False,
            unusual_length=False,
            first_active_user_id=earlier.first_active_user_id,
        )
        keeper.refresh_from_db()
    return keeper


def backfill_split_sessions(
    *,
    max_gap: timedelta = DEFAULT_MAX_GAP,
    apply: bool = False,
    limit: int | None = None,
    stdout=None,
) -> dict:
    pairs = find_split_pairs(max_gap=max_gap)
    if limit is not None:
        pairs = pairs[:limit]

    merged = 0
    for first, second in pairs:
        keeper, drop = choose_keeper(first, second)
        gap = abs((second.created_at - first.created_at).total_seconds())
        if stdout:
            stdout.write(
                f"  session {drop.pk} -> {keeper.pk}  room={first.room_id}  "
                f"gap={gap:.2f}s  users={first.u1_id}/{first.u2_id}"
            )
        if apply:
            merge_split_session_pair(first, second)
            merged += 1

    return {"found": len(pairs), "merged": merged}
