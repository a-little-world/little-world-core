"""Lobby queryset filters and DB-level metric annotations for random-call analytics."""

from __future__ import annotations

from datetime import datetime

from django.db.models import Count, IntegerField, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from management.models.profile import Profile

from video.analytics.queries import (
    accepted_proposal_bucket_q,
    expired_proposal_bucket_q,
    rejected_proposal_bucket_q,
)
from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching

# Annotation names — must match LobbyOccurrenceSnapshot fields read in snapshots.build_snapshots.
ANNOT_TOTAL_USERS = "total_users"
ANNOT_LEARNER_COUNT = "learner_count"
ANNOT_VOLUNTEER_COUNT = "volunteer_count"
ANNOT_PROPOSALS_TOTAL = "proposals_total"
ANNOT_PROPOSALS_ACCEPTED = "proposals_accepted"
ANNOT_PROPOSALS_REJECTED = "proposals_rejected"
ANNOT_PROPOSALS_EXPIRED = "proposals_expired"
ANNOT_COMPLETED_CALLS = "completed_calls"

DEFAULT_LOBBY_ORDERING = "-start_time"

ALLOWED_LOBBY_ORDERING = frozenset(
    {
        "start_time",
        "-start_time",
        "end_time",
        "-end_time",
        "name",
        "-name",
        ANNOT_TOTAL_USERS,
        f"-{ANNOT_TOTAL_USERS}",
        ANNOT_LEARNER_COUNT,
        f"-{ANNOT_LEARNER_COUNT}",
        ANNOT_VOLUNTEER_COUNT,
        f"-{ANNOT_VOLUNTEER_COUNT}",
        ANNOT_PROPOSALS_TOTAL,
        f"-{ANNOT_PROPOSALS_TOTAL}",
        ANNOT_PROPOSALS_ACCEPTED,
        f"-{ANNOT_PROPOSALS_ACCEPTED}",
        ANNOT_PROPOSALS_REJECTED,
        f"-{ANNOT_PROPOSALS_REJECTED}",
        ANNOT_PROPOSALS_EXPIRED,
        f"-{ANNOT_PROPOSALS_EXPIRED}",
        ANNOT_COMPLETED_CALLS,
        f"-{ANNOT_COMPLETED_CALLS}",
    }
)


def filtered_lobby_queryset(
    *,
    lobby_name: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> QuerySet[RandomCallLobby]:
    """Base lobby queryset for analytics list endpoints (no pagination or ordering)."""
    qs = RandomCallLobby.objects.all()
    if lobby_name is not None:
        qs = qs.filter(name=lobby_name)
    if from_dt is not None:
        qs = qs.filter(start_time__gte=from_dt)
    if to_dt is not None:
        qs = qs.filter(start_time__lte=to_dt)
    return qs


def _lobby_user_count_subquery(**filter_kwargs) -> Subquery:
    return Subquery(
        RandomCallLobbyUser.objects.filter(lobby_id=OuterRef("pk"), **filter_kwargs)
        .values("lobby_id")
        .annotate(_cnt=Count("id"))
        .values("_cnt")[:1],
        output_field=IntegerField(),
    )


def _lobby_user_distinct_count_subquery(**filter_kwargs) -> Subquery:
    return Subquery(
        RandomCallLobbyUser.objects.filter(lobby_id=OuterRef("pk"), **filter_kwargs)
        .values("lobby_id")
        .annotate(_cnt=Count("user_id", distinct=True))
        .values("_cnt")[:1],
        output_field=IntegerField(),
    )


def _proposal_count_subquery(*, bucket_q: Q | None = None, **filter_kwargs) -> Subquery:
    proposal_filter = Q(lobby_id=OuterRef("pk"))
    if bucket_q is not None:
        proposal_filter &= bucket_q
    if filter_kwargs:
        proposal_filter &= Q(**filter_kwargs)
    return Subquery(
        RandomCallMatching.objects.filter(proposal_filter)
        .values("lobby_id")
        .annotate(_cnt=Count("id"))
        .values("_cnt")[:1],
        output_field=IntegerField(),
    )


def annotate_lobby_metrics(qs: QuerySet[RandomCallLobby]) -> QuerySet[RandomCallLobby]:
    """Attach sortable per-lobby counts via separate subqueries (no join fan-out).

    Proposal bucket counts use mutually exclusive filters (status-first). Pending and
    dangling are filled in by ``build_snapshots`` because dangling needs per-lobby
    stale thresholds.
    """
    zero = IntegerField()
    return qs.annotate(
        **{
            ANNOT_TOTAL_USERS: Coalesce(_lobby_user_count_subquery(), 0, output_field=zero),
            ANNOT_LEARNER_COUNT: Coalesce(
                _lobby_user_distinct_count_subquery(user__profile__user_type=Profile.TypeChoices.LEARNER),
                0,
                output_field=zero,
            ),
            ANNOT_VOLUNTEER_COUNT: Coalesce(
                _lobby_user_distinct_count_subquery(user__profile__user_type=Profile.TypeChoices.VOLUNTEER),
                0,
                output_field=zero,
            ),
            ANNOT_PROPOSALS_TOTAL: Coalesce(_proposal_count_subquery(), 0, output_field=zero),
            ANNOT_PROPOSALS_ACCEPTED: Coalesce(
                _proposal_count_subquery(bucket_q=accepted_proposal_bucket_q()),
                0,
                output_field=zero,
            ),
            ANNOT_PROPOSALS_REJECTED: Coalesce(
                _proposal_count_subquery(bucket_q=rejected_proposal_bucket_q()),
                0,
                output_field=zero,
            ),
            ANNOT_PROPOSALS_EXPIRED: Coalesce(
                _proposal_count_subquery(bucket_q=expired_proposal_bucket_q()),
                0,
                output_field=zero,
            ),
            ANNOT_COMPLETED_CALLS: Coalesce(_proposal_count_subquery(completed=True), 0, output_field=zero),
        }
    )


def apply_lobby_ordering(qs: QuerySet[RandomCallLobby], ordering: str | None = None) -> QuerySet[RandomCallLobby]:
    ordering = ordering or DEFAULT_LOBBY_ORDERING
    if ordering not in ALLOWED_LOBBY_ORDERING:
        allowed = ", ".join(sorted(ALLOWED_LOBBY_ORDERING))
        raise ValueError(f"Invalid ordering '{ordering}'. Allowed: {allowed}")
    return qs.order_by(ordering)
