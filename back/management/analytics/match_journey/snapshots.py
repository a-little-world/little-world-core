"""Per-match overview snapshot — flat scalars for the public Match Overview page.

``build_snapshots`` is the entry point and the single-match helper wraps it, but it is
honestly a loop: each match costs its own set of queries. That is fine for the one
consumer today (a single match) and would not be for a list — see the note on
``build_snapshots`` before pointing this at a page of rows.

Call history is operational (viewer-relative direction) and is not on this dataclass.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.utils import timezone
from rest_framework import serializers

from management.analytics.match_journey.queries.activity import (
    DESIRED_DURATION_WEEKS,
    active_week_count,
    current_week,
    duration_aggregates,
    exact_total_minutes,
    journey_streaks,
    session_duration_seconds,
    weekly_activity_rows,
)
from management.match_success import success_token_threshold, tokens_from_total_minutes
from management.match_success.sessions import qualifying_sessions
from management.models.matches import Match

_DT = serializers.DateTimeField()


@dataclass(frozen=True)
class MatchOverviewSnapshot:
    match_uuid: UUID
    matched_at: datetime
    as_of: datetime
    current_week: int
    #: Weeks containing at least one qualifying call — the progress the ring shows.
    #: Not consecutive, and not the same as ``current_week``.
    active_weeks: int
    cycle_weeks: int
    is_free_play: bool
    calls: int
    total_minutes: float
    tokens: int
    token_threshold: int
    messages: int
    streak_weeks: int
    last_call_at: datetime | None


def _fmt(value: datetime | None):
    return None if value is None else _DT.to_representation(value)


def _snapshot_for_match(match: Match, *, as_of: datetime) -> MatchOverviewSnapshot:
    # One read of the qualifying sessions, reused for the aggregates and the week grid.
    # Fetching them three times — here, inside `weekly_activity_rows`, and again inside
    # `match_tokens` — was three LiveKit queries for one card.
    sessions = list(qualifying_sessions(match).only("created_at", "end_time"))
    aggregates = duration_aggregates(sessions)
    week_number = current_week(match, as_of=as_of)
    weekly = weekly_activity_rows(match, as_of=as_of, sessions=sessions)
    streaks = journey_streaks(weekly, week_number)
    # Summed from the week grid rather than a second COUNT over the same rows: every
    # message lands in some week, so the total and the grid can't drift apart.
    messages = sum(row["messages"] for row in weekly)
    total_minutes = exact_total_minutes(sessions)

    return MatchOverviewSnapshot(
        match_uuid=match.uuid,
        matched_at=match.created_at,
        as_of=as_of,
        current_week=week_number,
        active_weeks=active_week_count(weekly, week_number),
        cycle_weeks=DESIRED_DURATION_WEEKS,
        is_free_play=week_number > DESIRED_DURATION_WEEKS,
        calls=aggregates["count"],
        total_minutes=total_minutes,
        # Derived from the same total the card displays, not from a second SUM over the
        # same sessions — otherwise minutes and tokens are two answers to one question.
        # Exact, so this agrees with `match_tokens` at a band boundary.
        tokens=tokens_from_total_minutes(total_minutes),
        token_threshold=success_token_threshold(),
        messages=messages,
        streak_weeks=streaks["video_calls"]["current"],
        last_call_at=aggregates["last_started_at"],
    )


def build_snapshots(matches: Iterable[Match], *, as_of: datetime | None = None) -> dict[int, MatchOverviewSnapshot]:
    """Match pk → snapshot for every match in ``matches``.

    Costs two queries per match (qualifying sessions, pair messages) — it is a loop, not
    a batched query. The only caller today asks for one match, so this is the
    honest shape rather than a batch that was never exercised. Pointing it at a page
    means giving it a real batch form first: annotate the sessions and the message counts
    across all ids up front and hand each snapshot its slice (conventions §6).
    """
    as_of = as_of or timezone.now()
    return {match.pk: _snapshot_for_match(match, as_of=as_of) for match in matches}


def build_snapshot_for_match(match: Match, *, as_of: datetime | None = None) -> MatchOverviewSnapshot:
    return build_snapshots([match], as_of=as_of)[match.pk]


def snapshot_to_dict(snapshot: MatchOverviewSnapshot) -> dict:
    return {
        "match_uuid": str(snapshot.match_uuid),
        "matched_at": _fmt(snapshot.matched_at),
        "as_of": _fmt(snapshot.as_of),
        "current_week": snapshot.current_week,
        "active_weeks": snapshot.active_weeks,
        "cycle_weeks": snapshot.cycle_weeks,
        "is_free_play": snapshot.is_free_play,
        "calls": snapshot.calls,
        "total_minutes": snapshot.total_minutes,
        "tokens": snapshot.tokens,
        "token_threshold": snapshot.token_threshold,
        "messages": snapshot.messages,
        "streak_weeks": snapshot.streak_weeks,
        "last_call_at": _fmt(snapshot.last_call_at),
    }


def qualifying_call_history(match: Match) -> list[dict]:
    """Qualifying sessions, newest first. Direction is added by the view.

    No ``both_participated`` flag: ``qualifying_sessions`` only returns sessions where
    both people were active, so the field could never be False. A field with one possible
    value invites a reader to believe it has two.
    """
    sessions = (
        qualifying_sessions(match)
        .only(
            "uuid",
            "created_at",
            "end_time",
            "first_active_user_id",
        )
        .order_by("-created_at")
    )
    return [
        {
            "uuid": str(session.uuid),
            "started_at": _fmt(session.created_at),
            "duration_seconds": session_duration_seconds(session),
            "initiator_user_id": session.first_active_user_id,
        }
        for session in sessions
    ]
