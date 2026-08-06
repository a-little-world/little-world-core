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

Post-onboarding priority, highest first: success match, ongoing match, match takeoff,
open proposal, searching, idle. A user in a confirmed match with a *new* open proposal
is therefore counted as being in the match, not as awaiting a proposal — the reverse of
``journey_v2__pre_matching``, which had no state gate at all and took priority over
``journey_v2__match_takeoff``.

Fixes carried over the ``journey_v2__*`` lists these replace:

- ``num_matches`` in ``user_journey_filters`` sums two ``Count()`` calls over two
  multi-valued relations in one ``annotate()``, so the joins fan out and inflate each
  other. It is only safe against ``= 0``; ``user_searching_again``'s ``> 1`` test counts
  a user with one match on each side as two (conventions §6). V5 tests membership with
  a subquery instead of counting.
- ``get_user_involved`` materialised every ``(user1, user2)`` pair of *all* matches into
  a Python set per call — ``failed_matching`` did it ten times. V5 keeps them as
  subqueries scoped to the cohort.
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

from datetime import timedelta

from django.db.models import Exists, F, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from management.analytics.user_journey.queries import traits
from management.api.match_journey_filters import (
    completed_match,
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

_FILLED = traits.FILLED
_UNFILLED = traits.UNFILLED
_SEARCHING = traits.SEARCHING
_IDLE = traits.IDLE

# How long a user may search without a match before they count as one we failed to match.
UNMATCHED_AFTER_DAYS = 30


def _now(as_of=None):
    return as_of or timezone.now()


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _participates_in(pair_qs) -> Q:
    """``Q`` matching users on either side of ``pair_qs`` rows (``Match`` or ``ProposedMatch``).

    Both sides stay as ``id__in`` subqueries against a single-valued column, so nothing
    is materialised in Python and no multi-valued join is added to the outer query.
    """
    return Q(id__in=pair_qs.values("user1")) | Q(id__in=pair_qs.values("user2"))


def _cohort_matches(qs: QuerySet) -> QuerySet:
    """Matches with at least one participant in the cohort.

    Scoping first is what keeps the match-state subqueries off a full table scan.
    """
    return Match.objects.filter(Q(user1__in=qs) | Q(user2__in=qs))


def _non_support_matches(qs: QuerySet) -> QuerySet:
    return _cohort_matches(qs).filter(support_matching=False)


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
    return unbooked.filter(
        state__self_onboarding_started=True,
        state__self_onboarding_completed=False,
    ).exclude(id__in=_match_ineligible_learners(unbooked))


def signup_form_completed(qs: QuerySet, as_of=None) -> QuerySet:
    """Form complete and eligible, but onboarding has not been started.

    ``journey_v2__user_form_completed`` overlapped ``journey_v2__self_onboarding_started``
    here: it only required the absence of an appointment, so a user who had started
    self-onboarding without booking matched both buckets.
    """
    unbooked = _without_scheduled_appointment(_form_filled_pre_onboarding(qs), as_of)
    return unbooked.exclude(id__in=_match_ineligible_learners(unbooked)).exclude(
        state__self_onboarding_started=True,
        state__self_onboarding_completed=False,
    )


# ---------------------------------------------------------------------------
# Match-state predicates (post-onboarding priority order)
# ---------------------------------------------------------------------------


def _has_success_match(qs: QuerySet) -> Q:
    matches = _cohort_matches(qs)
    return _participates_in(completed_match(matches)) | _participates_in(match_free_play(matches))


def _has_ongoing_match(qs: QuerySet) -> Q:
    return _participates_in(match_ongoing(_cohort_matches(qs)))


def _has_takeoff_match(qs: QuerySet) -> Q:
    """Confirmed or newly proposed match that has not reached sustained contact."""
    matches = _cohort_matches(qs)
    return (
        _participates_in(match_unviewed(matches))
        | _participates_in(match_one_user_viewed(matches))
        | _participates_in(match_confirmed_no_contact(matches))
        | _participates_in(match_confirmed_single_party_contact(matches))
        | _participates_in(match_first_contact(matches))
    )


def _has_open_proposal(qs: QuerySet) -> Q:
    return _participates_in(matching_proposals())


def _has_failed_match(qs: QuerySet) -> Q:
    matches = _cohort_matches(qs)
    return (
        _participates_in(never_confirmed(matches))
        | _participates_in(no_contact(matches))
        | _participates_in(user_ghosted(matches))
        | _participates_in(contact_stopped(matches))
        | _participates_in(reported_or_removed_match(matches))
    )


def _still_matching(qs: QuerySet) -> QuerySet:
    """Post-onboarding users claimed by a higher-priority match-state bucket."""
    return post_onboarding(qs).filter(
        _has_success_match(qs) | _has_ongoing_match(qs) | _has_takeoff_match(qs) | _has_open_proposal(qs)
    )


# ---------------------------------------------------------------------------
# Phase: success
# ---------------------------------------------------------------------------


def success_free_play(qs: QuerySet) -> QuerySet:
    """Still in contact past the target match duration.

    ``journey_v2__happy_active`` was titled "Match Completed Free Play" and described as
    "completed a match but is still in contact". The query tests neither: a free-play
    match is one older than the target duration that is still ongoing.
    """
    return post_onboarding(qs).filter(_participates_in(match_free_play(_cohort_matches(qs))))


def success_match_completed(qs: QuerySet) -> QuerySet:
    """Completed a match and is not in a free-play continuation of one.

    Unlike ``journey_v2__happy_inactive`` this does not also exclude users with an
    ongoing match. That exclusion, combined with ``ongoing_non_completed_match``
    excluding users with a completed match, meant anyone holding both fell out of V4
    entirely. Here the completed match wins.
    """
    base = post_onboarding(qs)
    return base.filter(_participates_in(completed_match(_cohort_matches(qs)))).exclude(
        _participates_in(match_free_play(_cohort_matches(qs)))
    )


# ---------------------------------------------------------------------------
# Phase: active
# ---------------------------------------------------------------------------


def active_match_ongoing(qs: QuerySet) -> QuerySet:
    """In a match with sustained two-way contact."""
    return post_onboarding(qs).filter(_has_ongoing_match(qs)).exclude(_has_success_match(qs))


def active_match_takeoff(qs: QuerySet) -> QuerySet:
    """Has a match that has not reached sustained contact yet."""
    return (
        post_onboarding(qs)
        .filter(_has_takeoff_match(qs))
        .exclude(_has_success_match(qs))
        .exclude(_has_ongoing_match(qs))
    )


def active_proposed(qs: QuerySet) -> QuerySet:
    """Has an open match proposal awaiting a decision, and no match of their own yet."""
    return (
        post_onboarding(qs)
        .filter(_has_open_proposal(qs))
        .exclude(_has_success_match(qs))
        .exclude(_has_ongoing_match(qs))
        .exclude(_has_takeoff_match(qs))
    )


def _searching_without_match(qs: QuerySet) -> QuerySet:
    return (
        post_onboarding(qs)
        .filter(state__searching_state=_SEARCHING)
        .exclude(id__in=_still_matching(qs))
        .exclude(_participates_in(_non_support_matches(qs)))
    )


def active_searching_again(qs: QuerySet) -> QuerySet:
    """Back in the pool after an earlier match, with nothing currently in flight."""
    return (
        post_onboarding(qs)
        .filter(state__searching_state=_SEARCHING)
        .filter(_participates_in(_non_support_matches(qs)))
        .exclude(id__in=_still_matching(qs))
    )


def active_search_blocked(qs: QuerySet) -> QuerySet:
    """Searching for a first match but blocked from being matched by an eligibility rule.

    A0 German level or residence outside Germany. V4 had no bucket for these users:
    ``first_search_v2`` excluded them by default, so they left the partition and showed
    up only in the ``journey_v2__too_low_german_level`` segment (A0 only — the
    outside-Germany group was invisible entirely).
    """
    return _match_ineligible_learners(_searching_without_match(qs))


def active_first_search(qs: QuerySet, as_of=None) -> QuerySet:
    """Searching for a first match, eligible, and not yet overdue.

    Composite: the union of the five ``active_first_search_*`` cells below, which split
    it by what happened to the user's most recent proposal. Not a partition cell itself —
    it would double-count against its own members (``CatalogRole.COMPOSITE``).
    """
    searching = _searching_without_match(qs)
    return searching.exclude(id__in=_match_ineligible_learners(searching)).filter(
        date_joined__gte=_now(as_of) - timedelta(days=UNMATCHED_AFTER_DAYS)
    )


# ---------------------------------------------------------------------------
# First search, split by the outcome of the most recent proposal
# ---------------------------------------------------------------------------
#
# A user in `active_first_search` has no `Match` and no *open* proposal — both are
# excluded upstream by `_searching_without_match`. What they may have is a history of
# proposals that came to nothing, and V4 could not see it: `matching_proposals()` is
# `closed=False, expires_at >= now`, so anything rejected or expired simply stopped
# counting and the user was reported as though nothing had ever been tried for them.
#
# Ties are broken by *most recent proposal*, ordered on `potential_matching_created_at`
# — the only timestamp that is `auto_now_add` and therefore always populated
# (`rejected_at` and `expires_at` are both nullable).


def _standard_proposals_for_outer_user() -> QuerySet:
    """This user's STANDARD proposals, correlated to the outer query.

    Random-call and temporary proposals are excluded: they are a different product
    surface, and classifying a matching-funnel bucket by a random-call proposal would
    misreport it. ``ProposedMatch.get_open_proposals`` excludes temporary for the same
    reason.
    """
    return ProposedMatch.objects.filter(
        Q(user1=OuterRef("pk")) | Q(user2=OuterRef("pk")),
        match_type=MatchType.STANDARD,
    )


def _with_latest_proposal(qs: QuerySet) -> QuerySet:
    """Annotate each user with the outcome of their most recent standard proposal."""
    latest = _standard_proposals_for_outer_user().order_by("-potential_matching_created_at")
    return qs.annotate(
        _has_proposal=Exists(_standard_proposals_for_outer_user()),
        _latest_rejected=Subquery(latest.values("rejected")[:1]),
        _latest_expired=Subquery(latest.values("expired")[:1]),
        _latest_rejected_by=Subquery(latest.values("rejected_by_id")[:1]),
    )


def active_first_search_no_proposal(qs: QuerySet, as_of=None) -> QuerySet:
    """Searching, and we have never proposed anyone to them."""
    return _with_latest_proposal(active_first_search(qs, as_of)).filter(_has_proposal=False)


def active_first_search_rejected_by_them(qs: QuerySet, as_of=None) -> QuerySet:
    """Searching again after turning down the person we last proposed.

    Only the proposal's ``confirming_user`` is ever shown a proposal, so only they can
    reject one — every ``rejected_by`` in the data is that user. This cell is therefore
    mostly learners, since the learner confirms a standard match.
    """
    return _with_latest_proposal(active_first_search(qs, as_of)).filter(
        _has_proposal=True, _latest_rejected=True, _latest_rejected_by=F("id")
    )


def active_first_search_rejected_by_partner(qs: QuerySet, as_of=None) -> QuerySet:
    """Searching again after the person we last proposed turned *them* down.

    The counterpart of ``active_first_search_rejected_by_them``, and mostly volunteers.
    A rejected proposal with no ``rejected_by`` recorded would land here; there are none
    today, and the alternative is dropping the user out of the partition entirely.
    """
    return (
        _with_latest_proposal(active_first_search(qs, as_of))
        .filter(_has_proposal=True, _latest_rejected=True)
        .exclude(_latest_rejected_by=F("id"))
    )


def active_first_search_proposal_expired(qs: QuerySet, as_of=None) -> QuerySet:
    """Searching again because nobody decided on the last proposal in time."""
    return _with_latest_proposal(active_first_search(qs, as_of)).filter(
        _has_proposal=True, _latest_rejected=False, _latest_expired=True
    )


def active_first_search_proposal_closed(qs: QuerySet, as_of=None) -> QuerySet:
    """Searching again after the last proposal was closed without a decision.

    Not expiry and not a rejection — withdrawn, superseded, or closed by staff. Small
    but real: 32 of the closed proposals in production ended this way without ever
    becoming a match. Folding them into "expired" would put a wrong label on roughly a
    tenth of the users who have proposal history.
    """
    return _with_latest_proposal(active_first_search(qs, as_of)).filter(
        _has_proposal=True, _latest_rejected=False, _latest_expired=False
    )


# ---------------------------------------------------------------------------
# Phase: lapsed
# ---------------------------------------------------------------------------


def lapsed_unmatched(qs: QuerySet, as_of=None) -> QuerySet:
    """Eligible and still searching for a first match well past signup — we failed them.

    ``journey_v2__unmatched`` required a prematching appointment older than 30 days, so
    self-onboarded users could never enter it however long they waited. This measures
    from ``date_joined`` instead, which every user has.
    """
    searching = _searching_without_match(qs)
    return searching.exclude(id__in=_match_ineligible_learners(searching)).filter(
        date_joined__lt=_now(as_of) - timedelta(days=UNMATCHED_AFTER_DAYS)
    )


def lapsed_failed_matching(qs: QuerySet) -> QuerySet:
    """Stopped searching after one or more matches, none of which worked out."""
    return (
        post_onboarding(qs)
        .filter(state__searching_state=_IDLE)
        .filter(_participates_in(_non_support_matches(qs)))
        .exclude(id__in=_still_matching(qs))
    )


def lapsed_gave_up(qs: QuerySet) -> QuerySet:
    """Stopped searching without ever being matched."""
    return (
        post_onboarding(qs)
        .filter(state__searching_state=_IDLE)
        .exclude(id__in=_still_matching(qs))
        .exclude(_participates_in(_non_support_matches(qs)))
    )


def lapsed_failed_match_reasons(qs: QuerySet) -> QuerySet:
    """Drill-down: users whose matches ended in a recorded failure state.

    Not a partition bucket — it cuts across ``lapsed_failed_matching`` and the active
    phase, since a user can hold both a failed and a live match.
    """
    return post_onboarding(qs).filter(_has_failed_match(qs))


# ---------------------------------------------------------------------------
# Phase: past
# ---------------------------------------------------------------------------


def past_unresponsive(qs: QuerySet) -> QuerySet:
    """Still registered but flagged unresponsive, so excluded from matching.

    ``journey_v2__marked_unresponsive`` overlapped the success buckets, because
    ``happy_inactive`` and ``happy_active`` had no state gate at all.
    """
    return qs.filter(is_active=True, state__unresponsive=True)


def past_deleted_after_success(qs: QuerySet) -> QuerySet:
    """Left the platform having completed a match or reached free play.

    V4 folded these users into ``happy_inactive`` and subtracted them from
    ``journey_v2__user_deleted``, so the bucket labelled "User Was Deleted" excluded some
    deleted users and the success buckets counted people who had left. They are split
    out here so both readings are available and neither label lies.
    """
    return qs.filter(is_active=False).filter(_has_success_match(qs))


def past_deleted(qs: QuerySet) -> QuerySet:
    """Left the platform without completing a match."""
    return qs.filter(is_active=False).exclude(_has_success_match(qs))


def record_incomplete(qs: QuerySet) -> QuerySet:
    """Still registered but has no ``State`` row, so no journey state can be read.

    Every other live bucket filters on ``state__*``, which a null relation never matches.
    Without a bucket of its own such a user is unclassifiable and the partition can never
    balance — and a balance flag that is always false is one nobody reads (conventions §8).
    Naming it turns a silent gap into a number support can act on. Deleted accounts are
    counted as deleted whether or not they have a state row.
    """
    return qs.filter(is_active=True, state__isnull=True)
