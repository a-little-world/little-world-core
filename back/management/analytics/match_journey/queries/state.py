"""Mutually exclusive match-state queries — the ``match_state__`` namespace.

Clocks (pinned via ``as_of`` when provided)::

    Engagement window  = 4 weeks  — success_engaged vs success_dormant
    Failure cliff      = 10 weeks — in-flight / kickoff → failed_*

Priority (each cell excludes higher ones via its own predicates)::

    inactive: closing kind × stage reached
    → success_* (still ``active=True``)
    → failed_* (active, activity older than 10 weeks, not successful)
    → in_flight tokens_0..7
    → kickoff
    → unclassifiable

Inactive matches are split by *how* they ended, taken from the last ``report_unmatch``
entry — see ``CLOSING_KINDS``. Matches with no usable entry are ``unrecorded`` rather
than being folded into a deliberate outcome nobody performed.

Cells share a token map and the inactive breakdown through ``classification_run``; that
scope is per pass, never per thread, so nothing is memoised across requests.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from datetime import timedelta

from chat.models import Message
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.db.models.functions import Coalesce
from django.utils import timezone
from video.models import LivekitSession

from management.match_success import match_tokens_by_id, success_token_threshold, successful_match_ids

ENGAGEMENT_DAYS = 4 * 7  # 28 — still-in-contact window for successful matches
FAILURE_CLIFF_DAYS = 10 * 7  # 70 — no activity → failed


def _success_token_threshold() -> int:
    return success_token_threshold()


# Scratch space shared by the cells of a *single* classification pass. Thirty-odd cells
# each need the same token map and the same inactive breakdown, and recomputing them per
# cell is what made the per-row path unusable.
#
# Deliberately scoped to one run rather than to the thread: a thread-local cache is never
# invalidated, so a worker thread keeps serving the token counts it computed on its first
# request for the life of the process. Outside a run there is no cache at all, so a stale
# read is not possible by construction.
_RUN_CACHE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("match_state_run_cache", default=None)


@contextmanager
def classification_run():
    """Share derived maps across the cells of one partition/classification pass.

    Re-entrant: a nested call joins the outer run rather than starting a second cache.
    """
    if _RUN_CACHE.get() is not None:
        yield
        return
    token = _RUN_CACHE.set({})
    try:
        yield
    finally:
        _RUN_CACHE.reset(token)


def _run_cached(key, build):
    """Return ``build()``, memoised for the duration of the current run (if any)."""
    cache = _RUN_CACHE.get()
    if cache is None:
        return build()
    if key not in cache:
        cache[key] = build()
    return cache[key]


def _now(as_of=None):
    return as_of or timezone.now()


def _days_ago(days: int, as_of=None):
    return _now(as_of) - timedelta(days=days)


def _with_activity(qs: QuerySet) -> QuerySet:
    """Annotate coalesced activity time (last interaction, else match created)."""
    return qs.annotate(_activity_at=Coalesce("latest_interaction_at", "created_at"))


def _qualifying_session_exists() -> Exists:
    return Exists(
        LivekitSession.objects.filter(
            Q(u1_id=OuterRef("user1_id"), u2_id=OuterRef("user2_id"))
            | Q(u1_id=OuterRef("user2_id"), u2_id=OuterRef("user1_id")),
            both_have_been_active=True,
            created_at__gte=OuterRef("created_at"),
            end_time__isnull=False,
        )
    )


def _messages_both_ways() -> Q:
    u1_to_u2 = Message.objects.filter(sender=OuterRef("user1"), recipient=OuterRef("user2"))
    u2_to_u1 = Message.objects.filter(sender=OuterRef("user2"), recipient=OuterRef("user1"))
    return Q(Exists(u1_to_u2) & Exists(u2_to_u1))


def _messages_one_way() -> Q:
    u1_to_u2 = Message.objects.filter(sender=OuterRef("user1"), recipient=OuterRef("user2"))
    u2_to_u1 = Message.objects.filter(sender=OuterRef("user2"), recipient=OuterRef("user1"))
    return Q(Exists(u1_to_u2) & ~Exists(u2_to_u1)) | Q(~Exists(u1_to_u2) & Exists(u2_to_u1))


def _with_video_path(qs: QuerySet) -> QuerySet:
    """Mutual video call counter ≥ 1, or at least one qualifying LiveKit session."""
    return qs.filter(Q(total_mutal_video_calls_counter__gte=1) | _qualifying_session_exists())


def _without_video_path(qs: QuerySet) -> QuerySet:
    return qs.exclude(Q(total_mutal_video_calls_counter__gte=1) | _qualifying_session_exists())


def _tokens_map(qs: QuerySet) -> dict[int, int]:
    """Match ID → tokens. Memoised within a ``classification_run``, never beyond one."""
    return _run_cached(("tokens", *qs.query.sql_with_params()), lambda: match_tokens_by_id(qs))


def _ids_with_tokens(qs: QuerySet, *, minimum: int | None = None, exact: int | None = None) -> list[int]:
    tokens = _tokens_map(qs)
    if exact is not None:
        return [mid for mid, count in tokens.items() if count == exact]
    if minimum is not None:
        return [mid for mid, count in tokens.items() if count >= minimum]
    return list(tokens)


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def all_matches(qs: QuerySet) -> QuerySet:
    """Non-support matches — the partition denominator."""
    return qs.filter(support_matching=False)


# ---------------------------------------------------------------------------
# Shared gates
# ---------------------------------------------------------------------------


def _baseline(qs: QuerySet) -> QuerySet:
    return all_matches(qs)


def _successful_ids(qs: QuerySet) -> set[int]:
    """Matches that reached success, per ``match_success`` — the one definition.

    Not restated here. When this domain owned its own version of the rule and
    ``user_journey`` owned another, the two charts disagreed about 381 matches and put
    users in "stopped searching — after failed first match" while their match sat in
    "Successful — dormant".
    """
    return _run_cached(
        ("successful", *_baseline(qs).query.sql_with_params()), lambda: successful_match_ids(_baseline(qs))
    )


def _off_platform(qs: QuerySet) -> QuerySet:
    return _baseline(qs).filter(completed_off_plattform=True)


def _not_off_platform(qs: QuerySet) -> QuerySet:
    return _baseline(qs).filter(completed_off_plattform=False)


def _not_successful(qs: QuerySet) -> QuerySet:
    """Did not reach success by any route (off-platform included)."""
    return _baseline(qs).exclude(id__in=_successful_ids(qs))


# How a match ended, from the last ``report_unmatch`` entry. These are genuinely
# different outcomes and were previously collapsed into "removed", which asserted a
# deliberate removal for 168 matches that carry no closing record at all.
#
#   report        — a user reported the other
#   unmatch       — someone deliberately ended it
#   user_deleted  — an account went away underneath it
#   ghosted       — flagged as ghosting
#   unrecorded    — inactive with no (or malformed) closing entry: a data-quality signal,
#                   not an outcome. Named so nobody reads it as an action someone took.
CLOSING_KINDS = ("reported", "unmatched", "account_deleted", "ghosted", "unrecorded")
STAGES = ("successful", "before_success", "kickoff")

_KIND_BY_RAW = {
    "report": "reported",
    "unmatch": "unmatched",
    "user_deleted": "account_deleted",
    "ghosted": "ghosted",
}

_INACTIVE_KEYS = tuple(f"{kind}_{stage}" for kind in CLOSING_KINDS for stage in STAGES)


def _closing_kind(match) -> str:
    """Normalised closing kind, or ``unrecorded`` when the match carries no usable entry."""
    entries = match.report_unmatch if isinstance(match.report_unmatch, list) else []
    if not entries:
        return "unrecorded"
    last = entries[-1]
    if not isinstance(last, dict):
        return "unrecorded"
    return _KIND_BY_RAW.get(last.get("kind"), "unrecorded")


def _inactive_stage_ids(qs: QuerySet) -> dict[str, set[int]]:
    """Classify inactive matches into closing kind × stage reached.

    Closing kind and stage need the ``report_unmatch`` JSON and the token map, so this
    resolves every inactive row in one pass and the cells read from the result.
    """

    def build() -> dict[str, set[int]]:
        buckets: dict[str, set[int]] = {key: set() for key in _INACTIVE_KEYS}
        inactive = list(_baseline(qs).filter(active=False).only("id", "report_unmatch"))
        if not inactive:
            return buckets

        inactive_ids = [m.pk for m in inactive]
        succeeded = _successful_ids(qs)
        video_ids = set(_with_video_path(_baseline(qs).filter(id__in=inactive_ids)).values_list("id", flat=True))
        for match in inactive:
            if match.pk in succeeded:
                stage = "successful"
            elif match.pk in video_ids:
                stage = "before_success"
            else:
                stage = "kickoff"
            buckets[f"{_closing_kind(match)}_{stage}"].add(match.pk)
        return buckets

    return _run_cached(("inactive", *_baseline(qs).filter(active=False).query.sql_with_params()), build)


def _inactive_cell(qs: QuerySet, key: str) -> QuerySet:
    return qs.filter(id__in=_inactive_stage_ids(qs)[key])


def _within_failure_cliff(qs: QuerySet, as_of=None) -> QuerySet:
    return _with_activity(qs).filter(_activity_at__gte=_days_ago(FAILURE_CLIFF_DAYS, as_of))


def _past_failure_cliff(qs: QuerySet, as_of=None) -> QuerySet:
    return _with_activity(qs).filter(_activity_at__lt=_days_ago(FAILURE_CLIFF_DAYS, as_of))


def _engaged(qs: QuerySet, as_of=None) -> QuerySet:
    return qs.filter(latest_interaction_at__gte=_days_ago(ENGAGEMENT_DAYS, as_of))


def _dormant_engagement(qs: QuerySet, as_of=None) -> QuerySet:
    return qs.exclude(latest_interaction_at__gte=_days_ago(ENGAGEMENT_DAYS, as_of))


# ---------------------------------------------------------------------------
# Inactive — closing kind × stage reached (not under Failed)
# ---------------------------------------------------------------------------

_STAGE_PROSE = {
    "successful": "had already reached success",
    "before_success": "was in flight, under the success threshold",
    "kickoff": "was still in kickoff, with no mutual video",
}
_KIND_PROSE = {
    "reported": "a user reported the other",
    "unmatched": "someone deliberately ended it",
    "account_deleted": "a participant's account was deleted",
    "ghosted": "a participant was flagged as ghosting",
    "unrecorded": "why it ended was never recorded",
}


def _make_inactive_cell(kind: str, stage: str):
    key = f"{kind}_{stage}"

    def cell(qs: QuerySet, as_of=None) -> QuerySet:
        return _inactive_cell(qs, key)

    cell.__name__ = key
    cell.__qualname__ = key
    cell.__doc__ = f"Inactive because {_KIND_PROSE[kind]}; it {_STAGE_PROSE[stage]}."
    return cell


# One function per closing-kind × stage cell, built once at import and referenced
# everywhere — a new closing kind is one entry in CLOSING_KINDS, not fifteen edits.
INACTIVE_CELLS: dict[str, object] = {
    f"{kind}_{stage}": _make_inactive_cell(kind, stage) for kind in CLOSING_KINDS for stage in STAGES
}

reported_successful = INACTIVE_CELLS["reported_successful"]
reported_before_success = INACTIVE_CELLS["reported_before_success"]
reported_kickoff = INACTIVE_CELLS["reported_kickoff"]

unmatched_successful = INACTIVE_CELLS["unmatched_successful"]
unmatched_before_success = INACTIVE_CELLS["unmatched_before_success"]
unmatched_kickoff = INACTIVE_CELLS["unmatched_kickoff"]

account_deleted_successful = INACTIVE_CELLS["account_deleted_successful"]
account_deleted_before_success = INACTIVE_CELLS["account_deleted_before_success"]
account_deleted_kickoff = INACTIVE_CELLS["account_deleted_kickoff"]

ghosted_successful = INACTIVE_CELLS["ghosted_successful"]
ghosted_before_success = INACTIVE_CELLS["ghosted_before_success"]
ghosted_kickoff = INACTIVE_CELLS["ghosted_kickoff"]

unrecorded_successful = INACTIVE_CELLS["unrecorded_successful"]
unrecorded_before_success = INACTIVE_CELLS["unrecorded_before_success"]
unrecorded_kickoff = INACTIVE_CELLS["unrecorded_kickoff"]


# ---------------------------------------------------------------------------
# Success (still active)
# ---------------------------------------------------------------------------


def success_off_platform(qs: QuerySet, as_of=None) -> QuerySet:
    return _off_platform(qs).filter(active=True)


def success_engaged(qs: QuerySet, as_of=None) -> QuerySet:
    """Tokens ≥ 8 and activity within 4 weeks (message or call)."""
    pool = _not_off_platform(qs).filter(active=True, id__in=_successful_ids(qs))
    return _engaged(pool, as_of)


def success_dormant(qs: QuerySet, as_of=None) -> QuerySet:
    """Tokens ≥ 8 but no activity within 4 weeks."""
    pool = _not_off_platform(qs).filter(active=True, id__in=_successful_ids(qs))
    return _dormant_engagement(pool, as_of)


# ---------------------------------------------------------------------------
# Failed — 10-week cliff, not successful (active matches)
# ---------------------------------------------------------------------------


def _failed_active_pool(qs: QuerySet, as_of=None) -> QuerySet:
    return _past_failure_cliff(_not_successful(qs).filter(active=True), as_of)


def _failed_before_video(qs: QuerySet, as_of=None) -> QuerySet:
    return _without_video_path(_failed_active_pool(qs, as_of))


def failed_unviewed(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_before_video(qs, as_of).filter(confirmed=False, confirmed_by__isnull=True)


def failed_one_viewed(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_before_video(qs, as_of).filter(confirmed=False, confirmed_by__isnull=False)


def failed_confirmed_no_contact(qs: QuerySet, as_of=None) -> QuerySet:
    return (
        _failed_before_video(qs, as_of)
        .filter(
            confirmed=True,
            total_messages_counter=0,
            total_mutal_video_calls_counter=0,
        )
        .exclude(_messages_both_ways())
        .exclude(_messages_one_way())
    )


def failed_confirmed_one_way(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_before_video(qs, as_of).filter(confirmed=True).filter(_messages_one_way())


def failed_both_contacted_no_video(qs: QuerySet, as_of=None) -> QuerySet:
    # No `total_mutal_video_calls_counter=0` filter: `_failed_before_video` already
    # excluded the whole video path, counter included.
    return _failed_before_video(qs, as_of).filter(confirmed=True).filter(_messages_both_ways())


def _failed_with_video(qs: QuerySet, as_of=None) -> QuerySet:
    return _with_video_path(_failed_active_pool(qs, as_of))


def _failed_tokens(qs: QuerySet, n: int, as_of=None) -> QuerySet:
    pool = _failed_with_video(qs, as_of)
    return qs.filter(id__in=_ids_with_tokens(pool, exact=n))


def failed_tokens_0(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_tokens(qs, 0, as_of)


def failed_tokens_1(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_tokens(qs, 1, as_of)


def failed_tokens_2(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_tokens(qs, 2, as_of)


def failed_tokens_3(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_tokens(qs, 3, as_of)


def failed_tokens_4(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_tokens(qs, 4, as_of)


def failed_tokens_5(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_tokens(qs, 5, as_of)


def failed_tokens_6(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_tokens(qs, 6, as_of)


def failed_tokens_7(qs: QuerySet, as_of=None) -> QuerySet:
    return _failed_tokens(qs, 7, as_of)


# ---------------------------------------------------------------------------
# In flight — video started, tokens < 8, within failure cliff
# ---------------------------------------------------------------------------


def _in_flight_pool(qs: QuerySet, as_of=None) -> QuerySet:
    return _with_video_path(
        _within_failure_cliff(_not_successful(qs).filter(active=True), as_of).filter(confirmed=True)
    )


def _in_flight_tokens(qs: QuerySet, n: int, as_of=None) -> QuerySet:
    pool = _in_flight_pool(qs, as_of)
    # Cap at tokens < success: exact n for 0..7 only.
    return qs.filter(id__in=_ids_with_tokens(pool, exact=n))


def in_flight_tokens_0(qs: QuerySet, as_of=None) -> QuerySet:
    return _in_flight_tokens(qs, 0, as_of)


def in_flight_tokens_1(qs: QuerySet, as_of=None) -> QuerySet:
    return _in_flight_tokens(qs, 1, as_of)


def in_flight_tokens_2(qs: QuerySet, as_of=None) -> QuerySet:
    return _in_flight_tokens(qs, 2, as_of)


def in_flight_tokens_3(qs: QuerySet, as_of=None) -> QuerySet:
    return _in_flight_tokens(qs, 3, as_of)


def in_flight_tokens_4(qs: QuerySet, as_of=None) -> QuerySet:
    return _in_flight_tokens(qs, 4, as_of)


def in_flight_tokens_5(qs: QuerySet, as_of=None) -> QuerySet:
    return _in_flight_tokens(qs, 5, as_of)


def in_flight_tokens_6(qs: QuerySet, as_of=None) -> QuerySet:
    return _in_flight_tokens(qs, 6, as_of)


def in_flight_tokens_7(qs: QuerySet, as_of=None) -> QuerySet:
    return _in_flight_tokens(qs, 7, as_of)


def in_flight(qs: QuerySet, as_of=None) -> QuerySet:
    """COMPOSITE: union of in_flight token cells (for rollup checks)."""
    pool = _in_flight_pool(qs, as_of)
    tokens = _tokens_map(pool)
    ids = [mid for mid, count in tokens.items() if count < _success_token_threshold()]
    return qs.filter(id__in=ids)


# ---------------------------------------------------------------------------
# Kickoff — before video path, within failure cliff
# ---------------------------------------------------------------------------


def _kickoff_pool(qs: QuerySet, as_of=None) -> QuerySet:
    return _without_video_path(_within_failure_cliff(_not_successful(qs).filter(active=True), as_of))


def kickoff_unviewed(qs: QuerySet, as_of=None) -> QuerySet:
    return _kickoff_pool(qs, as_of).filter(confirmed=False, confirmed_by__isnull=True)


def kickoff_one_viewed(qs: QuerySet, as_of=None) -> QuerySet:
    return _kickoff_pool(qs, as_of).filter(confirmed=False, confirmed_by__isnull=False)


def kickoff_confirmed_no_contact(qs: QuerySet, as_of=None) -> QuerySet:
    return (
        _kickoff_pool(qs, as_of)
        .filter(confirmed=True, total_messages_counter=0, total_mutal_video_calls_counter=0)
        .exclude(_messages_both_ways())
        .exclude(_messages_one_way())
    )


def kickoff_confirmed_one_way(qs: QuerySet, as_of=None) -> QuerySet:
    return _kickoff_pool(qs, as_of).filter(confirmed=True).filter(_messages_one_way())


def kickoff_both_contacted_no_video(qs: QuerySet, as_of=None) -> QuerySet:
    # `_kickoff_pool` already excluded the video path, counter included.
    return _kickoff_pool(qs, as_of).filter(confirmed=True).filter(_messages_both_ways())


# ---------------------------------------------------------------------------
# Unclassifiable
# ---------------------------------------------------------------------------


#: Catalog key of the catch-all cell. Named here so ``unclassifiable`` can skip itself
#: when it walks the partition.
UNCLASSIFIABLE_LIST_ID = "match_state__unclassifiable"


def unclassifiable(qs: QuerySet, as_of=None) -> QuerySet:
    """Baseline members that no other cell claims — kept so the partition can balance.

    Walks the partition definition rather than a parallel list of cell functions. This is
    the one cell whose correctness depends on covering *every* other one, so a
    hand-maintained list beside the partition is precisely the wrong shape: add a cell,
    forget the list, and the balance check goes quiet instead of failing. Imported lazily
    because the catalog imports this module.
    """
    from management.analytics.match_journey.catalog import CATALOG
    from management.analytics.match_journey.partitions import MATCH_JOURNEY_V5

    with classification_run():
        claimed: set[int] = set()
        for list_id in MATCH_JOURNEY_V5.bucket_ids():
            if list_id == UNCLASSIFIABLE_LIST_ID:
                continue
            claimed |= set(CATALOG[list_id].build(qs, as_of=as_of).values_list("id", flat=True))
        return _baseline(qs).exclude(id__in=claimed)
