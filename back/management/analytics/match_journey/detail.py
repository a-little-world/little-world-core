"""Per-match retrieve extras for the admin match-detail page.

Query semantics live in ``queries/activity.py``. This module serializes those results
for the retrieve payload. Video calls are ``qualifying_sessions`` everywhere — the same
rule ``match_success`` uses for tokens — so MatchCard durations, the week grid, and
week-detail lists cannot disagree.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from management.analytics.match_journey.queries.activity import (
    DESIRED_DURATION_WEEKS,
    current_week,
    duration_aggregates,
    journey_streaks,
    last_message_times,
    pair_messages,
    session_duration_seconds,
    week_bounds,
    weekly_activity_rows,
)
from management.analytics.match_journey.queries.state import ENGAGEMENT_DAYS, FAILURE_CLIFF_DAYS
from management.match_success import success_token_threshold, tokens_from_total_minutes
from management.match_success.sessions import qualifying_sessions
from management.models.matches import Match

_DT = serializers.DateTimeField()

__all__ = [
    "DESIRED_DURATION_WEEKS",
    "current_week",
    "match_journey_stages",
    "match_stats_retrieve_extra",
    "match_weekly_activity_details",
    "match_weekly_activity_retrieve_extra",
    "week_bounds",
]


def _fmt(value: datetime | None):
    """Serialize a datetime the same way DRF does on the retrieve payload."""
    return None if value is None else _DT.to_representation(value)


def match_stats_retrieve_extra(match: Match) -> dict:
    """Read-only match stats for single-match GET. Not stored on Match.

    ``qualifying_video_call_count`` is deliberately *not* ``Match.total_mutal_video_calls_counter``
    and the two disagree on 89 of 800 matches. The stored counter is bumped the moment both
    people join a room (``video/livekit_webhook.py``), so it counts calls that never finished
    and random calls that happened before the pair were matched; it is also overwritten
    wholesale by ``Match.update_from_video_data``. The count here is the ``qualifying_sessions``
    rule — both active, finished, started on or after the match — which is what the durations
    beside it are computed from, so count and durations are answers about the same set of calls.

    Both are on the retrieve payload because the stored counter still drives filters and
    classification; when a display needs "how many calls did this match have", it is this one.
    """
    sessions = list(qualifying_sessions(match).only("created_at", "end_time"))
    aggregates = duration_aggregates(sessions)
    last_user1_at, last_user2_at = last_message_times(match)

    return {
        "last_video_call_at": _fmt(aggregates["last_started_at"]),
        "user1_last_message_at": _fmt(last_user1_at),
        "user2_last_message_at": _fmt(last_user2_at),
        "qualifying_video_call_count": aggregates["count"],
        "average_video_call_duration_seconds": aggregates["average_seconds"],
        "median_video_call_duration_seconds": aggregates["median_seconds"],
        "total_video_call_duration_seconds": aggregates["total_seconds"],
    }


def _stage(*, id: str, label: str, description: str, achieved: bool, achieved_at: datetime | None = None) -> dict:
    return {
        "id": id,
        "label": label,
        "description": description,
        "achieved": achieved,
        "achieved_at": _fmt(achieved_at),
        # Set on the one stage the match stopped at, if it failed. See `match_journey_stages`.
        "failed": False,
        "failed_at": None,
    }


def _token_progress(match: Match) -> tuple[int, int, datetime | None, datetime | None]:
    """Tokens, threshold, first qualifying call start, and the session end that first crossed success."""
    threshold = success_token_threshold()
    sessions = list(qualifying_sessions(match).order_by("end_time").only("created_at", "end_time"))
    total_minutes = 0.0
    success_at = None
    for session in sessions:
        total_minutes += (session.end_time - session.created_at).total_seconds() / 60.0
        if success_at is None and tokens_from_total_minutes(total_minutes) >= threshold:
            success_at = session.end_time
    first_call_at = min((session.created_at for session in sessions), default=None)
    return tokens_from_total_minutes(total_minutes), threshold, first_call_at, success_at


def _closing_entry(match: Match) -> dict | None:
    entries = match.report_unmatch if isinstance(match.report_unmatch, list) else []
    last = entries[-1] if entries else None
    return last if isinstance(last, dict) else None


def _closing_at(match: Match, entry: dict | None) -> datetime | None:
    if entry:
        parsed = parse_datetime(entry.get("time") or "")
        if parsed is not None:
            return parsed
    return match.updated_at


_FAILURE_BY_KIND = {
    "report": "A user reported the other.",
    "unmatch": "Someone ended the match.",
    "user_deleted": "A participant's account was deleted.",
    "ghosted": "A participant was flagged as ghosting.",
}


def match_journey_stages(match: Match, *, as_of: datetime | None = None) -> dict:
    """Ordered lifecycle timeline for a single match (retrieve only).

    Five steps: matched → first call → in-flight (token count) → success or failure
    (with the date that outcome landed) → engaged or dormant after that outcome.
    """
    now = as_of or timezone.now()
    created_at = match.created_at
    tokens, threshold, first_call_at, token_success_at = _token_progress(match)

    off_platform_at = match.completed_off_plattform_auto_marked_at if match.completed_off_plattform else None
    is_successful = match.completed_off_plattform or token_success_at is not None
    if is_successful:
        candidates = [moment for moment in (token_success_at, off_platform_at) if moment is not None]
        success_at = min(candidates) if candidates else created_at
    else:
        success_at = None

    has_first_call = first_call_at is not None or is_successful
    last_activity_at = match.latest_interaction_at or created_at
    cliff_at = last_activity_at + timedelta(days=FAILURE_CLIFF_DAYS)
    closing_entry = _closing_entry(match)
    closed_kind = closing_entry.get("kind") if closing_entry else None
    closed_at = _closing_at(match, closing_entry) if not match.active else None
    is_closed = not match.active
    is_failed = not is_successful and (is_closed or now >= cliff_at)
    failure_at = None
    failure_description = "No activity for 10 weeks before reaching success."
    if is_failed:
        failure_at = closed_at if is_closed else cliff_at
        if is_closed and closed_kind in _FAILURE_BY_KIND:
            failure_description = closing_entry.get("reason") or _FAILURE_BY_KIND[closed_kind]
        elif is_closed:
            failure_description = "Match ended without a recorded reason."

    if is_successful:
        outcome = _stage(
            id="success",
            label="Match success",
            description="Reached the match-success threshold.",
            achieved=True,
            achieved_at=success_at,
        )
    else:
        outcome = _stage(
            id="success",
            label="Match success",
            description=f"Reach {threshold} tokens, or complete off platform.",
            achieved=False,
        )

    is_engaged = last_activity_at >= now - timedelta(days=ENGAGEMENT_DAYS)
    if is_successful and is_engaged:
        engagement = _stage(
            id="engaged",
            label="Engaged",
            description="Activity within the last 4 weeks.",
            achieved=True,
            achieved_at=last_activity_at,
        )
    elif is_successful:
        engagement = _stage(
            id="dormant",
            label="Dormant",
            description="No activity for 4 weeks after success.",
            achieved=True,
            achieved_at=last_activity_at,
        )
    else:
        engagement = _stage(
            id="engaged",
            label="Engaged",
            description="Activity within 4 weeks after success.",
            achieved=False,
        )

    stages = [
        _stage(
            id="matched",
            label="Matched",
            description="Match created.",
            achieved=True,
            achieved_at=created_at,
        ),
        _stage(
            id="first_call",
            label="First call",
            description="First qualifying video call.",
            achieved=has_first_call,
            achieved_at=first_call_at,
        ),
        _stage(
            id="in_flight",
            label="In-flight",
            description=f"{tokens} of {threshold} tokens",
            achieved=has_first_call,
            achieved_at=None,
        ),
        outcome,
        engagement,
    ]

    # How far the match actually got, as a contiguous run — the stepper renders every
    # step before the active one as complete, so the *last* achieved index ticked stages
    # the match had skipped: a match that failed with no calls showed "First call ✓,
    # In-flight ✓" because its outcome stage was independently achieved.
    active_stage_index = next(
        (index for index, stage in enumerate(stages) if not stage["achieved"]),
        len(stages) - 1,
    )

    # A failure belongs to the step the match stopped at, not to a step of its own.
    if is_failed:
        stalled = stages[active_stage_index]
        stalled["failed"] = True
        stalled["failed_at"] = _fmt(failure_at)
        stalled["description"] = failure_description

    return {
        "stages": stages,
        "active_stage_index": active_stage_index,
        # Reports closure as it is. Suppressing this for successful matches while still
        # returning `closed_kind` and `closed_at` gave a payload that denied being closed
        # and named the reason it closed — a successful match that later ended is closed,
        # and `stages` already carries the success separately.
        "is_closed": is_closed,
        "closed_kind": closed_kind if is_closed else None,
        "closed_at": _fmt(closed_at) if is_closed else None,
    }


def match_weekly_activity_retrieve_extra(match: Match, *, as_of: datetime | None = None) -> dict:
    """Read-only activity breakdown for single-match GET."""
    as_of = as_of or timezone.now()
    week_number = current_week(match, as_of=as_of)
    rows = weekly_activity_rows(match, as_of=as_of)

    weekly_activity = [
        {
            "week": row["week"],
            "start_at": _fmt(row["start_at"]),
            "end_at": _fmt(row["end_at"]),
            "messages": row["messages"],
            "messages_user1": row["messages_user1"],
            "messages_user2": row["messages_user2"],
            "video_calls": row["video_calls"],
            "is_current_week": row["week"] == week_number,
            "is_free_play_week": row["week"] > DESIRED_DURATION_WEEKS,
        }
        for row in rows
    ]

    journey = {
        "current_week": week_number,
        "desired_duration_weeks": DESIRED_DURATION_WEEKS,
        "is_free_play": week_number > DESIRED_DURATION_WEEKS,
        "weekly_activity": weekly_activity,
        "streaks": journey_streaks(rows, week_number),
    }
    journey.update(match_journey_stages(match, as_of=as_of))

    return {"journey": journey}


def match_weekly_activity_details(match: Match, week: int) -> dict:
    """Read-only call/message breakdown for one journey week."""
    start_at, end_at = week_bounds(match, week)

    message_rows = (
        pair_messages(match)
        .filter(created__gte=start_at, created__lt=end_at)
        .select_related("sender__profile")
        .order_by("created")
    )
    messages = [
        {
            "created_at": _fmt(row.created),
            "sender_id": row.sender_id,
            "sender_name": row.sender.profile.first_name,
        }
        for row in message_rows
    ]

    sessions = qualifying_sessions(match).filter(created_at__gte=start_at, created_at__lt=end_at).order_by("created_at")
    video_calls = [
        {
            "created_at": _fmt(session.created_at),
            "end_time": _fmt(session.end_time),
            "duration_seconds": session_duration_seconds(session),
        }
        for session in sessions
    ]

    return {
        "week": week,
        "start_at": _fmt(start_at),
        "end_at": _fmt(end_at),
        "video_calls": video_calls,
        "messages": messages,
    }
