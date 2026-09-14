"""Range-level totals for random-call analytics.

One figure per *date range*, not per lobby: these answer "how much happened in this
window", which a page of per-lobby snapshots cannot express. Unique participants is the
clearest case — summing ``total_users`` across sessions counts a returning user once per
session she attended, which is attendance, not people.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from uuid import UUID

from video.analytics.queries import (
    batch_completed_call_durations,
    classify_proposal_pair,
    is_successful_call,
    rejected_proposal_bucket_q,
)
from video.analytics.snapshots import LobbyInstanceSnapshot, batch_lobby_participant_ids
from video.models import RandomCallLobby, RandomCallMatching


@dataclass(frozen=True)
class LobbyRangeTotals:
    """Flat scalars for one date range (§5) — no nested dicts, no request context."""

    lobby_count: int
    total_participants: int
    unique_participants: int
    completed_calls: int
    successful_calls: int
    total_call_duration_seconds: int
    median_call_duration_seconds: int | None

    # Rejected proposals, split by the pair's user types. Exhaustive and mutually
    # exclusive (§8): the three buckets sum to ``rejected_proposals``.
    rejected_proposals: int
    rejected_learner_learner: int
    rejected_learner_volunteer: int
    rejected_other: int


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def _rejected_pair_breakdown(lobby_ids: list[int]) -> tuple[int, int, int, int]:
    """(total, learner-learner, learner-volunteer, other) over the canonical rejected bucket.

    Uses ``rejected_proposal_bucket_q`` so the total reconciles with the
    ``proposals_rejected`` column on every row in the same response (§6), and
    ``classify_proposal_pair`` so the split means the same thing here as it does in the
    per-lobby proposal statistics.
    """
    rows = (
        RandomCallMatching.objects.filter(lobby_id__in=lobby_ids)
        .filter(rejected_proposal_bucket_q())
        .values_list("u1__profile__user_type", "u2__profile__user_type")
    )
    counts = Counter(classify_proposal_pair(u1_type, u2_type) for u1_type, u2_type in rows)

    learner_learner = counts["learner_learner"]
    learner_volunteer = counts["learner_volunteer"]
    other = counts["other"]
    return learner_learner + learner_volunteer + other, learner_learner, learner_volunteer, other


def build_lobby_range_totals(
    lobbies: list[RandomCallLobby],
    *,
    snapshots: dict[UUID, LobbyInstanceSnapshot],
) -> LobbyRangeTotals:
    """Totals over every lobby in the range.

    Participant and call counts are summed from the same snapshots the response returns,
    so the cards and the rows beneath them cannot disagree (§6).

    Durations come from ``batch_completed_call_durations`` — the same windowing the
    participants table uses — and only calls clearing ``MIN_SUCCESSFUL_CALL_SECONDS``
    contribute, so ``total_call_duration_seconds`` and the median describe exactly the
    calls ``successful_calls`` counts. ``completed_calls`` carries the unfiltered figure
    beside it, so the shortfall is reported rather than hidden (§7).
    """
    rows = [snapshots[lobby.uuid] for lobby in lobbies if lobby.uuid in snapshots]

    participants_by_lobby = batch_lobby_participant_ids(lobbies)
    unique_participants: set[int] = set()
    for user_ids in participants_by_lobby.values():
        unique_participants |= user_ids

    lobbies_by_id = {lobby.pk: lobby for lobby in lobbies}
    proposals_by_lobby: dict[int, list[RandomCallMatching]] = defaultdict(list)
    for proposal in RandomCallMatching.objects.filter(
        lobby_id__in=list(lobbies_by_id),
        accepted=True,
        completed=True,
    ):
        proposals_by_lobby[proposal.lobby_id].append(proposal)

    durations = batch_completed_call_durations(proposals_by_lobby, lobbies_by_id=lobbies_by_id)
    successful_durations = [seconds for seconds in durations.values() if is_successful_call(seconds)]

    rejected_total, learner_learner, learner_volunteer, rejected_other = _rejected_pair_breakdown(list(lobbies_by_id))

    return LobbyRangeTotals(
        lobby_count=len(rows),
        total_participants=sum(row.total_users for row in rows),
        unique_participants=len(unique_participants),
        completed_calls=sum(row.completed_calls for row in rows),
        successful_calls=sum(row.successful_calls for row in rows),
        total_call_duration_seconds=sum(successful_durations),
        median_call_duration_seconds=_median(successful_durations),
        rejected_proposals=rejected_total,
        rejected_learner_learner=learner_learner,
        rejected_learner_volunteer=learner_volunteer,
        rejected_other=rejected_other,
    )


def lobby_range_totals_to_dict(totals: LobbyRangeTotals) -> dict:
    return asdict(totals)
