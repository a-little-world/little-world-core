"""Which LiveKit sessions count toward match tokens.

A call only counts when both participants were active (``both_have_been_active``), the
session has finished, and it belongs to the match pair on or after the match was created.

**The batch form is the primitive.** ``annotate_total_call_minutes`` adds the aggregate to
a whole queryset in one query; the single-match helpers read that annotation when it is
present and fall back to their own query when it is not. Writing the single-row case first
and bolting batching on later is how one rule ends up with two implementations that drift
— and a serialized page of 25 matches cost 75 queries before this existed.
"""

from datetime import timedelta

from django.db.models import DurationField, ExpressionWrapper, F, OuterRef, Q, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from video.models import LivekitSession

#: Annotation name carrying total qualifying call time as a ``timedelta``.
#: Read by ``total_call_minutes``; nothing outside this module should depend on the name.
TOTAL_CALL_TIME_ANNOTATION = "_match_total_call_time"

#: Docs page copy. Keep in lockstep with ``qualifying_sessions`` / the batch subquery.
QUALIFYING_CALL_RULE = "A call only counts when both participants were active (both_have_been_active)."

_SESSION_DURATION = ExpressionWrapper(F("end_time") - F("created_at"), output_field=DurationField())


def qualifying_sessions(match) -> QuerySet:
    """Finished mutual sessions for the match pair (both users were active).

    Filters on ``user1_id`` / ``user2_id`` rather than ``match.user1`` / ``match.user2``:
    the attribute form dereferences both foreign keys, which cost two extra queries per
    match on every serialized row.
    """
    return LivekitSession.objects.filter(
        Q(u1_id=match.user1_id, u2_id=match.user2_id) | Q(u1_id=match.user2_id, u2_id=match.user1_id),
        both_have_been_active=True,
        created_at__gte=match.created_at,
        end_time__isnull=False,
    )


def _total_call_time_subquery() -> Subquery:
    """Correlated sum of qualifying session duration for the outer ``Match`` row."""
    sessions = (
        LivekitSession.objects.filter(
            Q(u1=OuterRef("user1_id"), u2=OuterRef("user2_id")) | Q(u1=OuterRef("user2_id"), u2=OuterRef("user1_id")),
            both_have_been_active=True,
            created_at__gte=OuterRef("created_at"),
            end_time__isnull=False,
        )
        # Group every matching session into a single row so the subquery returns one value.
        .annotate(_group=Value(1))
        .values("_group")
        .annotate(_total=Sum(_SESSION_DURATION))
        .values("_total")
    )
    return Subquery(sessions, output_field=DurationField())


def annotate_total_call_minutes(qs: QuerySet) -> QuerySet:
    """Annotate a ``Match`` queryset with its total qualifying call time, in one query.

    Matches with no qualifying sessions get zero rather than ``None``, so callers never
    branch on a missing value.
    """
    return qs.annotate(
        **{
            TOTAL_CALL_TIME_ANNOTATION: Coalesce(
                _total_call_time_subquery(),
                Value(timedelta(0), output_field=DurationField()),
            )
        }
    )


def total_call_duration(match) -> timedelta:
    """Total qualifying call time for one match.

    Uses the batch annotation when the match came from an annotated queryset, so a
    serialized page costs one query instead of one per row.
    """
    annotated = getattr(match, TOTAL_CALL_TIME_ANNOTATION, None)
    if annotated is not None:
        return annotated
    total = qualifying_sessions(match).aggregate(total=Sum(_SESSION_DURATION))["total"]
    return total or timedelta(0)


def total_call_minutes(match) -> float:
    return total_call_duration(match).total_seconds() / 60.0


def total_call_minutes_by_match_id(qs: QuerySet) -> dict[int, float]:
    """Match ID → total qualifying call minutes, for every match in ``qs``. One query."""
    annotated = annotate_total_call_minutes(qs).values_list("id", TOTAL_CALL_TIME_ANNOTATION)
    return {match_id: (total or timedelta(0)).total_seconds() / 60.0 for match_id, total in annotated}
