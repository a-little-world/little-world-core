"""Per-match activity queries — week clock, messages, qualifying calls, streaks.

A video call counts only when it is a ``qualifying_sessions`` row: both users were
active, the session has finished, and it started on or after the match was created.
That is the same rule ``match_success`` uses for tokens. Stats, the week grid, and
week-detail lists all read from that queryset so they cannot disagree.

**Messages are not scoped that way, on purpose.** ``pair_messages`` is every message
between the two people, whenever it was sent. Calls are scoped because a call feeds
tokens and therefore the definition of success, and success has to start at the match;
a message count is just "how much have these two talked", and a pair who met through a
random call and talked before being matched really did talk. 4,317 messages across 419
matches predate their match, almost all from that flow. So a week grid can carry
messages in week 1 that arrived before ``created_at`` — ``week_for_timestamp`` floors
to week 1 — and the two columns answer slightly different questions by design.

Weeks are 1-indexed from ``Match.created_at``. That clock is the planned 10-week
journey, not the 10-week inactivity cliff in ``queries/state.py``.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from datetime import datetime, timedelta

from chat.models import Message
from django.db.models import Max, Q, QuerySet
from django.utils import timezone
from video.models import LivekitSession

from management.match_success.sessions import qualifying_sessions
from management.models.matches import Match

#: Planned match duration in weeks, counted from ``Match.created_at``.
#: Distinct from ``FAILURE_CLIFF_DAYS`` (10 weeks since last activity).
DESIRED_DURATION_WEEKS = 10


def current_week(match: Match, *, as_of: datetime | None = None) -> int:
    """1-indexed week since match creation. ``as_of`` defaults to now."""
    as_of = as_of or timezone.now()
    return max(((as_of - match.created_at).days // 7) + 1, 1)


def week_bounds(match: Match, week: int) -> tuple[datetime, datetime]:
    if week < 1:
        raise ValueError("week must be >= 1")
    match_start = match.created_at
    return match_start + timedelta(weeks=week - 1), match_start + timedelta(weeks=week)


def week_for_timestamp(match: Match, timestamp: datetime) -> int:
    return max(((timestamp - match.created_at).days // 7) + 1, 1)


def pair_messages(match: Match) -> QuerySet:
    """Messages between the match pair. Do not use Chat.get_chat() — it can miss older rows."""
    return Message.objects.filter(
        Q(sender_id=match.user1_id, recipient_id=match.user2_id)
        | Q(sender_id=match.user2_id, recipient_id=match.user1_id)
    )


def session_duration_seconds(session: LivekitSession) -> int:
    return max(int((session.end_time - session.created_at).total_seconds()), 0)


def exact_total_minutes(sessions: list[LivekitSession]) -> float:
    """Total call minutes, unrounded — the input the token bands expect.

    ``duration_aggregates`` floors each session to whole seconds because it feeds
    human-readable durations. Tokens must not be computed from that: the bands are
    thresholds, so a match sitting a fraction of a second above one would earn a token
    from ``match_tokens`` (a DB ``SUM`` over the same rows) and not from here. Same rows,
    same arithmetic as the SQL sum, no extra query.
    """
    return sum((session.end_time - session.created_at).total_seconds() for session in sessions) / 60.0


def duration_aggregates(sessions: list[LivekitSession]) -> dict:
    """Count / total / average / median / last start from one session list.

    Empty list → null duration fields so the card can show ``n/a`` rather than zero.
    """
    if not sessions:
        return {
            "count": 0,
            "total_seconds": None,
            "average_seconds": None,
            "median_seconds": None,
            "last_started_at": None,
        }

    durations = [session_duration_seconds(session) for session in sessions]
    total = sum(durations)
    return {
        "count": len(sessions),
        "total_seconds": total,
        "average_seconds": round(total / len(sessions)),
        "median_seconds": round(statistics.median(durations)),
        "last_started_at": max(session.created_at for session in sessions),
    }


def last_message_times(match: Match) -> tuple[datetime | None, datetime | None]:
    last_user1 = pair_messages(match).filter(sender_id=match.user1_id).aggregate(ts=Max("created"))["ts"]
    last_user2 = pair_messages(match).filter(sender_id=match.user2_id).aggregate(ts=Max("created"))["ts"]
    return last_user1, last_user2


def empty_week(match: Match, week: int) -> dict:
    start_at, end_at = week_bounds(match, week)
    return {
        "week": week,
        "start_at": start_at,
        "end_at": end_at,
        "messages": 0,
        "messages_user1": 0,
        "messages_user2": 0,
        "video_calls": 0,
    }


def weekly_activity_rows(
    match: Match,
    *,
    as_of: datetime | None = None,
    sessions: list[LivekitSession] | None = None,
) -> list[dict]:
    """One row per journey week from week 1 through max(current, planned duration).

    ``sessions`` lets a caller that already loaded the qualifying sessions pass them in
    rather than triggering a second read of the same rows.
    """
    as_of = as_of or timezone.now()
    week_number = current_week(match, as_of=as_of)
    weeks_to_show = max(week_number, DESIRED_DURATION_WEEKS)
    activity_by_week = {week: empty_week(match, week) for week in range(1, weeks_to_show + 1)}

    for timestamp, sender_id in pair_messages(match).values_list("created", "sender_id"):
        week = week_for_timestamp(match, timestamp)
        activity = activity_by_week.setdefault(week, empty_week(match, week))
        activity["messages"] += 1
        if sender_id == match.user1_id:
            activity["messages_user1"] += 1
        elif sender_id == match.user2_id:
            activity["messages_user2"] += 1

    session_starts = (
        [session.created_at for session in sessions]
        if sessions is not None
        else list(qualifying_sessions(match).values_list("created_at", flat=True))
    )
    for timestamp in session_starts:
        week = week_for_timestamp(match, timestamp)
        activity = activity_by_week.setdefault(week, empty_week(match, week))
        activity["video_calls"] += 1

    return sorted(activity_by_week.values(), key=lambda item: item["week"])


def active_week_count(weekly_activity: list[dict], week_number: int) -> int:
    """Journey weeks so far that contain at least one qualifying video call.

    The planned cycle is ten weeks *of calling*, not ten weeks on the calendar, and the
    weeks do not have to be consecutive — a pair who miss a week have not lost anything,
    they simply have not banked that week yet. This is what the progress ring measures;
    ``current_week`` (calendar) and ``streak_stats`` (consecutive) both answer different
    questions and neither is the progress number.
    """
    return sum(1 for row in weekly_activity if row["week"] <= week_number and row["video_calls"] > 0)


def streak_stats(
    weekly_activity: list[dict],
    predicate: Callable[[dict], bool],
    week_number: int,
) -> dict:
    """Current and record consecutive-week streaks over elapsed journey weeks.

    Current walks backwards from ``week_number`` and stops at the first miss, **except**
    the current week itself: that week is still in progress, so its being empty does not
    break anything. Counting it as a miss meant an eight-week streak read 0 every Monday
    until someone sent a message — the number went down while nothing had gone wrong.
    Any *completed* week without activity still ends the run.

    Record is the longest run anywhere in the elapsed window.
    """
    elapsed = sorted(
        (row for row in weekly_activity if row["week"] <= week_number),
        key=lambda row: row["week"],
    )
    running = 0
    record = 0
    record_start: int | None = None
    record_end: int | None = None
    running_start: int | None = None

    for row in elapsed:
        if predicate(row):
            if running == 0:
                running_start = row["week"]
            running += 1
            if running > record:
                record = running
                record_start = running_start
                record_end = row["week"]
            continue
        running = 0
        running_start = None

    current = 0
    for index, row in enumerate(reversed(elapsed)):
        if predicate(row):
            current += 1
            continue
        if index == 0 and row["week"] == week_number:
            # The current week is still running; nothing has been missed yet.
            continue
        break

    return {
        "current": current,
        "record": record,
        "record_start_week": record_start,
        "record_end_week": record_end,
    }


def journey_streaks(weekly_activity: list[dict], week_number: int) -> dict:
    return {
        "messages": streak_stats(weekly_activity, lambda row: row["messages"] > 0, week_number),
        "video_calls": streak_stats(weekly_activity, lambda row: row["video_calls"] > 0, week_number),
        "any_activity": streak_stats(
            weekly_activity,
            lambda row: row["messages"] > 0 or row["video_calls"] > 0,
            week_number,
        ),
    }
