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


def match_journey_stages(match: Match, week_number: int, desired_duration_weeks: int) -> dict:
    """Ordered lifecycle timeline for a single match (retrieve only).

    The "happy path" is: matched -> first contact -> ongoing -> completed -> free play.
    A reported/unmatched match terminates in a final "closed" step, and any later
    happy-path steps that were never reached are dropped so the progress bar shortens.
    """
    created_at = match.created_at

    has_interaction = bool(
        match.first_interaction_at or match.total_messages_counter or match.total_mutal_video_calls_counter
    )
    is_completed = bool(match.completed or match.completed_off_plattform)
    is_free_play = week_number > desired_duration_weeks and match.active

    report_entries = match.report_unmatch if isinstance(match.report_unmatch, list) else []
    closing_entry = report_entries[-1] if report_entries else None
    # A naturally completed match is a success, not a "closed" failure, even if inactive.
    is_closed = (not match.active) and closing_entry is not None and not is_completed

    completed_at = match.completed_off_plattform_auto_marked_at
    if is_completed and completed_at is None:
        completed_at = created_at + timedelta(weeks=desired_duration_weeks)

    free_play_at = created_at + timedelta(weeks=desired_duration_weeks) if is_free_play else None

    happy_path = [
        {
            "id": "matched",
            "label": "Matched",
            "description": "Match created.",
            "achieved": True,
            "achieved_at": _fmt(created_at),
        },
        {
            "id": "first_contact",
            "label": "First contact",
            "description": "Both people started interacting.",
            "achieved": has_interaction,
            "achieved_at": _fmt(match.first_interaction_at),
        },
        {
            "id": "ongoing",
            "label": "Ongoing",
            "description": f"Active within the planned {desired_duration_weeks} week journey.",
            "achieved": has_interaction,
            "achieved_at": None,
        },
        {
            "id": "completed",
            "label": "Completed",
            "description": "Completed on or off platform.",
            "achieved": is_completed,
            "achieved_at": _fmt(completed_at),
        },
        {
            "id": "free_play",
            "label": "Free play",
            "description": f"Active beyond week {desired_duration_weeks}.",
            "achieved": is_free_play,
            "achieved_at": _fmt(free_play_at),
        },
    ]

    achieved_indexes = [index for index, stage in enumerate(happy_path) if stage["achieved"]]
    furthest_index = achieved_indexes[-1] if achieved_indexes else 0

    closed_kind = None
    closed_at = None
    if is_closed and closing_entry is not None:
        closed_kind = closing_entry.get("kind")
        parsed_closed_time = parse_datetime(closing_entry.get("time") or "")
        closed_at = _fmt(parsed_closed_time or match.updated_at)

        closed_label = {
            "report": "Reported",
            "unmatch": "Unmatched",
            "user_deleted": "User deleted",
        }.get(closed_kind, "Closed")

        stages = happy_path[: furthest_index + 1]
        stages.append(
            {
                "id": "closed",
                "label": closed_label,
                "description": closing_entry.get("reason") or "Match was reported or unmatched.",
                "achieved": True,
                "achieved_at": closed_at,
            }
        )
        active_stage_index = len(stages) - 1
    else:
        stages = happy_path
        active_stage_index = furthest_index

    return {
        "stages": stages,
        "active_stage_index": active_stage_index,
        "is_closed": is_closed,
        "closed_kind": closed_kind,
        "closed_at": closed_at,
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
    journey.update(match_journey_stages(match, week_number, DESIRED_DURATION_WEEKS))

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
