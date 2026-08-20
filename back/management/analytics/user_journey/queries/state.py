"""Mutually exclusive current-state queries — the ``state__`` namespace.

Every user in the cohort should land in **exactly one** bucket. Each query therefore
carries its own exclusions rather than relying on the order the registry happens to
evaluate them in, so ``assert_partition_disjoint_strict`` can actually fail when two
definitions drift into overlap (conventions §8 — an invariant that cannot fail is not
an invariant).

Top-level split of the cohort::

    is_active=False                          → past_deleted_after_success | past_deleted
    is_active=True,  unresponsive=True       → past_unresponsive
    is_active=True,  unresponsive=False      → pre-onboarding  | post-onboarding buckets

Post-onboarding priority, highest first: successful first match (absorbing 2×2) →
first-match kickoff/ongoing (never succeeded) → open proposal / searching / idle
(pre-match if never matched, else after failed first). A user in a live match with a
*new* open proposal is therefore counted in the match, not as awaiting a proposal —
the reverse of ``journey_v2__pre_matching``, which had no state gate at all and took
priority over ``journey_v2__match_takeoff``.

Fixes carried over the ``journey_v2__*`` lists these replace:

- ``num_matches`` in ``user_journey_filters`` sums two ``Count()`` calls over two
  multi-valued relations in one ``annotate()``, so the joins fan out and inflate each
  other. It is only safe against ``= 0``; ``user_searching_again``'s ``> 1`` test counts
  a user with one match on each side as two (conventions §6). V5 tests membership with
  a subquery instead of counting.
- ``get_user_involved`` materialised every ``(user1, user2)`` pair of *all* matches into
  a Python set per call — ``failed_matching`` did it ten times. V5 keeps them as
  correlated ``EXISTS`` subqueries (see ``_participates_in``), so nothing is pulled into
  Python and the participation lookup uses the ``user1_id`` / ``user2_id`` indexes.
- A0-German and outside-Germany learners were excluded from some buckets and not
  others, so they were double-counted in one phase and absent from another. V5 gives
  them explicit state buckets and no bucket silently drops them.
- ``journey_v2__too_low_german_level`` is a cohort trait, not a journey state, and
  overlapped every other bucket. It is not part of V5 (conventions §3).

Several names here mirror one in ``queries/funnel.py`` — ``signup_form_completed``
against ``users_who_completed_form``, for instance. They are not duplicates: the funnel
counts everyone who reached a stage, this counts only those who got no further. Both
answers are wanted; what must never diverge is the underlying trait, which is why
eligibility comes from ``traits`` rather than being restated here.
"""

import contextvars
from contextlib import contextmanager

from django.db.models import Exists, F, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from management.analytics.user_journey.queries import traits
from management.api.match_journey_filters import (
    contact_stopped,
    match_confirmed_no_contact,
    match_confirmed_single_party_contact,
    match_first_contact,
    match_free_play,
    match_one_user_viewed,
    match_ongoing,
    match_unviewed,
    matching_proposals,
    never_confirmed,
    no_contact,
    reported_or_removed_match,
    user_ghosted,
)
from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType, ProposedMatch
from management.self_onboarding_progress import self_onboarding_in_progress_q

_FILLED = traits.FILLED
_UNFILLED = traits.UNFILLED
_SEARCHING = traits.SEARCHING
_IDLE = traits.IDLE

# Scratch for one classify/compute pass. ``successful_matches`` annotates LiveKit call
# time; embedding that in ``_has_success_match`` meant every success-gated cell re-paid
# the SUM (≈21 queries on user retrieve). The run precomputes participant user ids once.
_RUN_CACHE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("user_state_run_cache", default=None)


@contextmanager
def classification_run(root_qs: QuerySet | None = None):
    """Share derived success participants across the cells of one user-partition pass.

    ``root_qs`` is optional here, unlike the match-journey run where it is required. The
    difference is what happens without it: there, cells would read a shared token map
    whose scope came from whichever cell asked first, and silently under-count. Here the
    only cached value is the success-participant set, and its absence makes
    ``_has_success_match`` fall back to the ``EXISTS`` form — the same answer, just
    without the saved annotate. Degrading to slow-but-correct needs no guard; degrading
    to fast-but-wrong does.
    """
    if _RUN_CACHE.get() is not None:
        yield
        return
    cache: dict = {}
    if root_qs is not None:
        cache["success_user_ids"] = _compute_success_user_ids(root_qs)
    token = _RUN_CACHE.set(cache)
    try:
        yield
    finally:
        _RUN_CACHE.reset(token)


def _compute_success_user_ids(user_qs: QuerySet) -> frozenset[int]:
    """User ids who participate in a successful non-support match — one annotate."""
    from management.match_success import successful_matches

    matches = successful_matches(
        Match.objects.filter(support_matching=False).filter(Q(user1__in=user_qs) | Q(user2__in=user_qs))
    )
    out: set[int] = set()
    for user1_id, user2_id in matches.values_list("user1_id", "user2_id"):
        out.add(user1_id)
        out.add(user2_id)
    return frozenset(out)


def _now(as_of=None):
    return as_of or timezone.now()


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _participates_in(pair_qs) -> Q:
    """``Q`` matching users on either side of ``pair_qs`` rows (``Match`` or ``ProposedMatch``).

    One correlated ``EXISTS`` rather than ``id__in(user1) | id__in(user2)``. Both forms
    are correct, but the ``id__in`` pair emits the whole of ``pair_qs`` twice, and these
    predicates compose — ``_has_live_match`` is fourteen of them. Nesting that made
    ``state__first_search_no_proposal`` a 34 KB query with 48 scans of the match table.
    ``EXISTS`` keeps one copy and drives off the ``user1_id`` / ``user2_id`` indexes.
    """
    return Q(Exists(pair_qs.filter(Q(user1=OuterRef("pk")) | Q(user2=OuterRef("pk")))))


def _all_matches() -> QuerySet:
    """Every match. The cohort restriction lives in the outer query, not here.

    These predicates are always composed onto a queryset that is already the cohort, so a
    cohort member's matches are found whether or not the match set was pre-filtered.
    Pre-filtering with ``Q(user1__in=qs) | Q(user2__in=qs)`` embedded the cohort subquery
    inside all fourteen nested predicates and roughly doubled the cost of every
    match-state bucket, for no change in membership (conventions §6).
    """
    return Match.objects.all()


def _non_support_matches() -> QuerySet:
    return _all_matches().filter(support_matching=False)


def _match_ineligible_learners(qs: QuerySet) -> QuerySet:
    """Learners blocked from matching by A0 German level or residence outside Germany.

    Shares its predicate with the funnel's ``learners_ineligible_for_onboarding`` via
    ``traits``, so the two constructs cannot answer this question differently. Only the
    context differs: the funnel asks it of form-complete users awaiting onboarding, the
    partition asks it of whoever a given bucket is about.
    """
    return qs.filter(traits.is_match_ineligible_learner())


# ---------------------------------------------------------------------------
# Phase gates
# ---------------------------------------------------------------------------


def live_users(qs: QuerySet) -> QuerySet:
    """Cohort members still on the platform and not flagged unresponsive."""
    return qs.filter(is_active=True, state__unresponsive=False)


def pre_onboarding(qs: QuerySet) -> QuerySet:
    """Live users who have not both filled the registration form and finished onboarding.

    Splitting on the pair rather than on ``is_onboarded`` alone keeps users who were
    marked onboarded by a backfill while their form is still unfilled inside the signup
    phase, where their form state has a bucket. Gating on ``is_onboarded=False`` alone
    would move them to the active phase, where every bucket requires a filled form, and
    they would fall out of the partition.
    """
    return live_users(qs).exclude(state__user_form_state=_FILLED, state__is_onboarded=True)


def post_onboarding(qs: QuerySet) -> QuerySet:
    """Live users who filled the registration form and finished onboarding."""
    return live_users(qs).filter(state__user_form_state=_FILLED, state__is_onboarded=True)


# The partition's denominator is `funnel__all` — the same cohort the funnel starts
# from, so there is one baseline entry rather than an identical second one.

# ---------------------------------------------------------------------------
# Phase: signup (live, onboarding not finished)
# ---------------------------------------------------------------------------


def _form_filled_pre_onboarding(qs: QuerySet) -> QuerySet:
    return pre_onboarding(qs).filter(state__user_form_state=_FILLED)


def _with_future_appointment(qs: QuerySet, as_of=None) -> QuerySet:
    return qs.filter(id__in=qs.filter(prematchingappointment__end_time__gt=_now(as_of)).values("id"))


def _with_past_appointment(qs: QuerySet, as_of=None) -> QuerySet:
    return qs.filter(id__in=qs.filter(prematchingappointment__end_time__lte=_now(as_of)).values("id"))


def _without_scheduled_appointment(qs: QuerySet, as_of=None) -> QuerySet:
    """Users with no onboarding appointment carrying a resolvable end time.

    Defined as the complement of the future/past pair rather than
    ``prematchingappointment__isnull=True`` so a row with a null ``end_time`` still lands
    in a bucket instead of disappearing from the partition.
    """
    return qs.exclude(id__in=_with_future_appointment(qs, as_of)).exclude(id__in=_with_past_appointment(qs, as_of))


def signup_created(qs: QuerySet) -> QuerySet:
    """Registered but has not verified their email address yet."""
    return pre_onboarding(qs).filter(state__user_form_state=_UNFILLED, state__email_authenticated=False)


def signup_email_verified(qs: QuerySet) -> QuerySet:
    """Email verified; the registration form is still unfilled."""
    return pre_onboarding(qs).filter(state__user_form_state=_UNFILLED, state__email_authenticated=True)


def signup_onboarding_booked(qs: QuerySet, as_of=None) -> QuerySet:
    """Form complete with an onboarding call booked in the future."""
    return _with_future_appointment(_form_filled_pre_onboarding(qs), as_of)


def signup_no_show(qs: QuerySet, as_of=None) -> QuerySet:
    """Booked an onboarding call, did not attend, and has not rebooked."""
    filled = _form_filled_pre_onboarding(qs)
    return _with_past_appointment(filled, as_of).exclude(id__in=_with_future_appointment(filled, as_of))


def signup_ineligible(qs: QuerySet, as_of=None) -> QuerySet:
    """Form complete, no call booked, blocked from onboarding by an eligibility rule.

    A0 German level or residence outside Germany, unless ``force_match_eligible``.
    In V4 these users had no state bucket at all — they appeared only in the global
    ``journey_v2__too_low_german_level`` segment, which was not part of the partition.
    """
    return _match_ineligible_learners(_without_scheduled_appointment(_form_filled_pre_onboarding(qs), as_of))


def signup_self_onboarding(qs: QuerySet, as_of=None) -> QuerySet:
    """Self-onboarding started but not finished, with no call booked."""
    unbooked = _without_scheduled_appointment(_form_filled_pre_onboarding(qs), as_of)
    return unbooked.filter(self_onboarding_in_progress_q()).exclude(id__in=_match_ineligible_learners(unbooked))


def signup_form_completed(qs: QuerySet, as_of=None) -> QuerySet:
    """Form complete and eligible, but onboarding has not been started.

    ``journey_v2__user_form_completed`` overlapped ``journey_v2__self_onboarding_started``
    here: it only required the absence of an appointment, so a user who had started
    self-onboarding without booking matched both buckets.
    """
    unbooked = _without_scheduled_appointment(_form_filled_pre_onboarding(qs), as_of)
    return unbooked.exclude(id__in=_match_ineligible_learners(unbooked)).exclude(self_onboarding_in_progress_q())


# ---------------------------------------------------------------------------
# Match-state predicates
# ---------------------------------------------------------------------------
#
# Priority for live onboarded users (highest first):
#   successful first match (absorbing) → first-match kickoff/ongoing →
#   open proposal / searching / idle (pre-match if never matched, else after failed)


# Each of these is a correlated predicate about the user in the outer query, so none of
# them takes the cohort — see ``_all_matches``. The uniform zero-argument signature is the
# point: when some took ``qs`` and some did not, ``_has_open_proposal`` was silently the
# only unscoped one and nothing said whether that was a decision or an oversight.


def _has_success_match() -> Q:
    """In a match that reached success. Absorbing milestone.

    Delegates to ``match_success`` — the one definition of match success — rather than
    restating it. This used to be the V4 ``completed_match | match_free_play`` pair, which
    is the *comparison-only* v0 rule, while ``match_journey`` classified the same matches
    with the active v1 rule. The two disagreed about 381 matches and produced users sitting
    in "stopped searching — after failed first match" whose match read "Successful —
    dormant". Non-support only, matching the match-journey baseline.

    Inside a ``classification_run``, participant ids are precomputed once so cells do not
    each embed ``successful_matches``' LiveKit SUM annotate.
    """
    cache = _RUN_CACHE.get()
    if cache is not None and "success_user_ids" in cache:
        return Q(pk__in=cache["success_user_ids"])

    from management.match_success import successful_matches

    return _participates_in(successful_matches(_non_support_matches()))


def _has_ongoing_match() -> Q:
    return _participates_in(match_ongoing(_all_matches()))


def _has_takeoff_match() -> Q:
    """Confirmed or newly started match that has not reached sustained contact."""
    matches = _all_matches()
    return (
        _participates_in(match_unviewed(matches))
        | _participates_in(match_one_user_viewed(matches))
        | _participates_in(match_confirmed_no_contact(matches))
        | _participates_in(match_confirmed_single_party_contact(matches))
        | _participates_in(match_first_contact(matches))
    )


def _has_live_match() -> Q:
    """Any match still in flight — kickoff, sustained, or free-play."""
    return _has_takeoff_match() | _has_ongoing_match() | _participates_in(match_free_play(_all_matches()))


def _has_open_proposal() -> Q:
    return _participates_in(matching_proposals())


def _has_match_history() -> Q:
    return _participates_in(_non_support_matches())


def _has_failed_match() -> Q:
    matches = _all_matches()
    return (
        _participates_in(never_confirmed(matches))
        | _participates_in(no_contact(matches))
        | _participates_in(user_ghosted(matches))
        | _participates_in(contact_stopped(matches))
        | _participates_in(reported_or_removed_match(matches))
    )


def _never_succeeded(qs: QuerySet) -> QuerySet:
    return post_onboarding(qs).exclude(_has_success_match())


def _claimed_by_live_match_or_proposal(qs: QuerySet) -> QuerySet:
    return post_onboarding(qs).filter(_has_live_match() | _has_open_proposal() | _has_success_match())


def _searching_without_match(qs: QuerySet) -> QuerySet:
    """Searching, never matched, nothing in flight — the pre-match searching pool."""
    return (
        post_onboarding(qs)
        .filter(state__searching_state=_SEARCHING)
        .exclude(id__in=_claimed_by_live_match_or_proposal(qs))
        .exclude(_has_match_history())
    )


# ---------------------------------------------------------------------------
# Phase: successful first match (absorbing) — 2×2 live × searching
# ---------------------------------------------------------------------------


def _succeeded(qs: QuerySet) -> QuerySet:
    return post_onboarding(qs).filter(_has_success_match())


def success_ongoing_searching(qs: QuerySet) -> QuerySet:
    """Completed a successful first match; still in a live match and searching again."""
    return _succeeded(qs).filter(_has_live_match(), state__searching_state=_SEARCHING)


def success_ongoing_settled(qs: QuerySet) -> QuerySet:
    """Completed a successful first match; still in a live match and not searching.

    The quiet success cell — matched and settled, no rematch activity.
    """
    return _succeeded(qs).filter(_has_live_match()).exclude(state__searching_state=_SEARCHING)


def success_searching(qs: QuerySet) -> QuerySet:
    """Completed a successful first match; no live match, back in the pool."""
    return _succeeded(qs).filter(state__searching_state=_SEARCHING).exclude(_has_live_match())


def success_idle(qs: QuerySet) -> QuerySet:
    """Completed a successful first match; no live match and not searching."""
    return _succeeded(qs).exclude(_has_live_match()).exclude(state__searching_state=_SEARCHING)


# ---------------------------------------------------------------------------
# Phase: first match in flight (never yet succeeded)
# ---------------------------------------------------------------------------


def first_match_kickoff(qs: QuerySet) -> QuerySet:
    """In a first-success attempt that has not reached sustained contact yet."""
    return _never_succeeded(qs).filter(_has_takeoff_match())


def first_match_ongoing(qs: QuerySet) -> QuerySet:
    """In a first-success attempt past kickoff — sustained contact, or free play.

    Together with ``first_match_kickoff`` this covers *everything* ``_has_live_match``
    covers, which is the property the partition depends on: every other never-succeeded
    cell excludes users with a live match.
    """
    return _never_succeeded(qs).filter(_has_live_match()).exclude(_has_takeoff_match())


# ---------------------------------------------------------------------------
# Phase: after failed first match(es) — never succeeded, has match history
# ---------------------------------------------------------------------------


def rematch_proposed(qs: QuerySet) -> QuerySet:
    """Open rematch proposal after failed first match(es); nothing live yet."""
    return _never_succeeded(qs).filter(_has_match_history(), _has_open_proposal()).exclude(_has_live_match())


def searching_after_failed(qs: QuerySet) -> QuerySet:
    """Back in the pool after failed first match(es); no open proposal, nothing live."""
    return (
        _never_succeeded(qs)
        .filter(state__searching_state=_SEARCHING)
        .filter(_has_match_history())
        .exclude(id__in=_claimed_by_live_match_or_proposal(qs))
    )


def stopped_after_failed(qs: QuerySet) -> QuerySet:
    """Idle after failed first match(es); not searching, nothing in flight."""
    return (
        _never_succeeded(qs)
        .filter(state__searching_state=_IDLE)
        .filter(_has_match_history())
        .exclude(id__in=_claimed_by_live_match_or_proposal(qs))
    )


# ---------------------------------------------------------------------------
# Phase: pre-match (never had a Match)
# ---------------------------------------------------------------------------


def proposed_never_matched(qs: QuerySet) -> QuerySet:
    """Open proposal and has never had a real match."""
    return _never_succeeded(qs).filter(_has_open_proposal()).exclude(_has_match_history()).exclude(_has_live_match())


def active_search_blocked(qs: QuerySet) -> QuerySet:
    """Searching for a first match but blocked from being matched by an eligibility rule."""
    return _match_ineligible_learners(_searching_without_match(qs))


def active_first_search(qs: QuerySet) -> QuerySet:
    """Searching for a first match and eligible — never matched, nothing in flight.

    Composite of the five proposal-outcome cells. Not a partition cell itself.
    """
    searching = _searching_without_match(qs)
    return searching.exclude(id__in=_match_ineligible_learners(searching))


def _standard_proposals_for_outer_user() -> QuerySet:
    return ProposedMatch.objects.filter(
        Q(user1=OuterRef("pk")) | Q(user2=OuterRef("pk")),
        match_type=MatchType.STANDARD,
    )


def _with_latest_proposal(qs: QuerySet) -> QuerySet:
    latest = _standard_proposals_for_outer_user().order_by("-potential_matching_created_at")
    return qs.annotate(
        _has_proposal=Exists(_standard_proposals_for_outer_user()),
        _latest_rejected=Subquery(latest.values("rejected")[:1]),
        _latest_expired=Subquery(latest.values("expired")[:1]),
        _latest_rejected_by=Subquery(latest.values("rejected_by_id")[:1]),
    )


def active_first_search_no_proposal(qs: QuerySet) -> QuerySet:
    return _with_latest_proposal(active_first_search(qs)).filter(_has_proposal=False)


def active_first_search_rejected_by_them(qs: QuerySet) -> QuerySet:
    return _with_latest_proposal(active_first_search(qs)).filter(
        _has_proposal=True, _latest_rejected=True, _latest_rejected_by=F("id")
    )


def active_first_search_rejected_by_partner(qs: QuerySet) -> QuerySet:
    return (
        _with_latest_proposal(active_first_search(qs))
        .filter(_has_proposal=True, _latest_rejected=True)
        .exclude(_latest_rejected_by=F("id"))
    )


def active_first_search_proposal_expired(qs: QuerySet) -> QuerySet:
    return _with_latest_proposal(active_first_search(qs)).filter(
        _has_proposal=True, _latest_rejected=False, _latest_expired=True
    )


def active_first_search_proposal_closed(qs: QuerySet) -> QuerySet:
    return _with_latest_proposal(active_first_search(qs)).filter(
        _has_proposal=True, _latest_rejected=False, _latest_expired=False
    )


def lapsed_gave_up(qs: QuerySet) -> QuerySet:
    """Stopped searching without ever being matched."""
    return (
        post_onboarding(qs)
        .filter(state__searching_state=_IDLE)
        .exclude(_has_match_history())
        .exclude(id__in=_claimed_by_live_match_or_proposal(qs))
    )


def lapsed_failed_match_reasons(qs: QuerySet) -> QuerySet:
    """Drill-down: onboarded users with at least one match in a recorded failure state."""
    return post_onboarding(qs).filter(_has_failed_match())


# ---------------------------------------------------------------------------
# Phase: past
# ---------------------------------------------------------------------------


def past_unresponsive_after_success(qs: QuerySet) -> QuerySet:
    """Marked unresponsive after a successful first match."""
    return qs.filter(is_active=True, state__unresponsive=True).filter(_has_success_match())


def past_unresponsive(qs: QuerySet) -> QuerySet:
    """Marked unresponsive without a successful first match."""
    return qs.filter(is_active=True, state__unresponsive=True).exclude(_has_success_match())


def past_deleted_after_success(qs: QuerySet) -> QuerySet:
    """Left the platform after a successful first match."""
    return qs.filter(is_active=False).filter(_has_success_match())


def past_deleted(qs: QuerySet) -> QuerySet:
    """Left the platform without a successful first match."""
    return qs.filter(is_active=False).exclude(_has_success_match())


def record_incomplete(qs: QuerySet) -> QuerySet:
    """Still registered but has no ``State`` row, so no journey state can be read."""
    return qs.filter(is_active=True, state__isnull=True)
