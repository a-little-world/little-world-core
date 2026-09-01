import calendar
import statistics
from datetime import date, datetime, time, timedelta

from django.db.models import F, Min, OuterRef, Q, Subquery
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from management.helpers import IsAdminOrMatchingUser
from management.models.courses import Course, UserCourseProgress
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.profile import Profile
from management.models.unconfirmed_matches import MatchType, ProposedMatch
from management.models.user import User
from management.self_onboarding_progress import (
    self_onboarding_completed_at_for_user,
    self_onboarding_progress_prefetch,
)

MATCH_TYPE_ALL = "all"
SUPPORTED_MATCH_TYPES = {MATCH_TYPE_ALL, MatchType.STANDARD, MatchType.RANDOM_CALL}


def _parse_date_input(value, default):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return default
    return datetime.strptime(value, "%Y-%m-%d").date()


def _inclusive_datetime_range(start_date, end_date):
    start_datetime = datetime.combine(start_date, time.min)
    end_datetime = datetime.combine(end_date, time.max)
    if timezone.is_naive(start_datetime):
        start_datetime = timezone.make_aware(start_datetime)
    if timezone.is_naive(end_datetime):
        end_datetime = timezone.make_aware(end_datetime)
    return start_datetime, end_datetime


def _stacked_percentages(counts, total):
    """Return percentages that sum to exactly 100.00 using largest remainder."""
    if total == 0:
        return [0.0] * len(counts)

    basis = 10000
    exact = [count * basis / total for count in counts]
    floored = [int(value) for value in exact]
    remainder = basis - sum(floored)
    order = sorted(range(len(counts)), key=lambda index: exact[index] - floored[index], reverse=True)
    for index in range(remainder):
        floored[order[index % len(counts)]] += 1
    return [value / 100 for value in floored]


def _accessible_users(user):
    users = User.objects.all()
    if not user.is_staff:
        users = users.filter(id__in=user.managed_users_queryset(active_only=False).values("id"))
    return users


def _base_proposal_queryset(accessible_users, start_datetime, end_datetime):
    return ProposedMatch.objects.filter(
        Q(user1__in=accessible_users) | Q(user2__in=accessible_users),
        potential_matching_created_at__range=[start_datetime, end_datetime],
    ).exclude(match_type=MatchType.TEMPORARY)


def _filter_proposals_by_match_type(proposals, match_type):
    if match_type != MATCH_TYPE_ALL:
        return proposals.filter(match_type=match_type)
    return proposals


def _proposal_outcome_summary(proposals):
    total_proposals = proposals.count()
    accepted_count = proposals.filter(closed=True, rejected=False, expired=False).count()
    expired_count = proposals.filter(expired=True).count()
    rejected_count = proposals.filter(rejected=True).count()
    pending_count = proposals.filter(closed=False, rejected=False, expired=False).count()
    accepted_percentage, expired_percentage, rejected_percentage, pending_percentage = _stacked_percentages(
        [accepted_count, expired_count, rejected_count, pending_count],
        total_proposals,
    )

    return {
        "total_proposals": total_proposals,
        "accepted_count": accepted_count,
        "accepted_percentage": accepted_percentage,
        "expired_count": expired_count,
        "expired_percentage": expired_percentage,
        "rejected_count": rejected_count,
        "rejected_percentage": rejected_percentage,
        "pending_count": pending_count,
        "pending_percentage": pending_percentage,
    }


def _iter_month_starts(start_date, end_date):
    current = start_date.replace(day=1)
    while current <= end_date:
        yield current
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def _month_end(month_start):
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start.replace(day=last_day)


def _average_days(values):
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _median_days(values):
    if not values:
        return None
    return round(statistics.median(values), 1)


def _outcome_waiting_summary(day_values):
    return {
        "count": len(day_values),
        "average_days": _average_days(day_values),
        "median_days": _median_days(day_values),
    }


def _waiting_time_summary(day_values, still_waiting_count=0, cohort_count=0):
    return {
        "count": cohort_count,
        "average_days": _average_days(day_values),
        "median_days": _median_days(day_values),
        "still_waiting_count": still_waiting_count,
        "completed_count": len(day_values) - still_waiting_count,
    }


def _first_proposal_subquery(match_type):
    proposals = ProposedMatch.objects.filter(
        confirming_user=OuterRef("confirming_user"),
    ).exclude(match_type=MatchType.TEMPORARY)
    if match_type != MATCH_TYPE_ALL:
        proposals = proposals.filter(match_type=match_type)
    return proposals.order_by("potential_matching_created_at").values("id")[:1]


def _filter_to_learner_first_proposals(proposals, match_type):
    return (
        proposals.filter(
            confirming_user__isnull=False,
            confirming_user__profile__user_type=Profile.TypeChoices.LEARNER,
        )
        .annotate(first_proposal_id=Subquery(_first_proposal_subquery(match_type)))
        .filter(id=F("first_proposal_id"))
        .select_related("confirming_user__state")
        .prefetch_related(self_onboarding_progress_prefetch("confirming_user__"))
    )


def _proposal_outcome_bucket(proposal):
    if proposal.closed and not proposal.rejected and not proposal.expired:
        return "accepted"
    if proposal.expired:
        return "expired"
    if proposal.rejected:
        return "rejected"
    return "pending"


def _waiting_days_at_proposal(proposal, earliest_prematch_end_by_user):
    ready_at = _user_onboarded_at(proposal.confirming_user, earliest_prematch_end_by_user)
    if ready_at is None:
        return None
    return max((proposal.potential_matching_created_at - ready_at).days, 0)


def _first_proposal_outcome_waiting_time(proposals, match_type):
    first_proposals = list(_filter_to_learner_first_proposals(proposals, match_type))
    confirming_user_ids = [proposal.confirming_user_id for proposal in first_proposals]
    earliest_prematch_end_by_user = _earliest_prematch_end_by_user(confirming_user_ids)

    waiting_days_by_outcome = {
        "accepted": [],
        "expired": [],
        "rejected": [],
    }
    excluded_count = 0
    pending_count = 0

    for proposal in first_proposals:
        outcome = _proposal_outcome_bucket(proposal)
        if outcome == "pending":
            pending_count += 1
            continue

        waiting_days = _waiting_days_at_proposal(proposal, earliest_prematch_end_by_user)
        if waiting_days is None:
            excluded_count += 1
            continue

        waiting_days_by_outcome[outcome].append(waiting_days)

    return {
        "accepted": _outcome_waiting_summary(waiting_days_by_outcome["accepted"]),
        "expired": _outcome_waiting_summary(waiting_days_by_outcome["expired"]),
        "rejected": _outcome_waiting_summary(waiting_days_by_outcome["rejected"]),
        "pending_count": pending_count,
        "excluded_count": excluded_count,
        "total_first_proposals": len(first_proposals),
    }


def _user_onboarded_at(user, earliest_prematch_end_by_user=None):
    """
    When the user finished onboarding and became eligible for matching.

    Uses stored state timestamps (earliest completion). Prematch appointment rows are
    only a fallback for legacy users missing those fields — and we use the earliest
    appointment, not the latest, because volunteers may have follow-up prematch calls
    long after their first match.
    """
    state = user.state
    candidates = []
    if state.onboarding_call_completed_at:
        candidates.append(state.onboarding_call_completed_at)
    self_completed_at = self_onboarding_completed_at_for_user(user)
    if self_completed_at:
        candidates.append(self_completed_at)
    if candidates:
        return min(candidates)

    if earliest_prematch_end_by_user is not None:
        return earliest_prematch_end_by_user.get(user.pk)

    earliest_pre_match = (
        PreMatchingAppointment.objects.filter(user=user, end_time__isnull=False).order_by("end_time").first()
    )
    return earliest_pre_match.end_time if earliest_pre_match else None


def _earliest_prematch_end_by_user(user_ids):
    if not user_ids:
        return {}
    rows = (
        PreMatchingAppointment.objects.filter(user_id__in=user_ids, end_time__isnull=False)
        .values("user_id")
        .annotate(earliest_end=Min("end_time"))
    )
    return {row["user_id"]: row["earliest_end"] for row in rows}


def _waiting_days_for_user(user, event_at, now, earliest_prematch_end_by_user=None):
    ready_at = _user_onboarded_at(user, earliest_prematch_end_by_user)
    if ready_at is None:
        return None
    end_at = event_at if event_at is not None else now
    return max((end_at - ready_at).days, 0)


def _onboarded_users_in_range(accessible_users, start_datetime, end_datetime):
    """Users who completed onboarding within the selected date range."""
    start_date = start_datetime.date()
    end_date = end_datetime.date()
    candidates = (
        accessible_users.filter(state__is_onboarded=True)
        .filter(
            UserCourseProgress.exists_for_user(
                slug=Course.SELF_ONBOARDING_SLUG,
                completed=True,
                completed_at__range=(start_datetime, end_datetime),
            )
            | Q(state__self_onboarding_completed_at__range=[start_date, end_date])
            | Q(state__onboarding_call_completed_at__range=[start_datetime, end_datetime])
        )
        .select_related("state", "profile")
        .prefetch_related(self_onboarding_progress_prefetch())
    )

    candidate_ids = list(candidates.values_list("pk", flat=True))
    earliest_prematch_end_by_user = _earliest_prematch_end_by_user(candidate_ids)

    cohort_ids = []
    for user in candidates.iterator(chunk_size=500):
        onboarded_at = _user_onboarded_at(user, earliest_prematch_end_by_user)
        if onboarded_at and start_datetime <= onboarded_at <= end_datetime:
            cohort_ids.append(user.pk)

    # Same prefetch as `candidates`: callers run `_user_onboarded_at` over this cohort,
    # and rebuilding the queryset without it dropped back to a query per user.
    cohort = (
        accessible_users.filter(id__in=cohort_ids)
        .select_related("state", "profile")
        .prefetch_related(self_onboarding_progress_prefetch())
    )
    return cohort, earliest_prematch_end_by_user


def _first_proposal_queryset(match_type):
    proposals = ProposedMatch.objects.filter(confirming_user=OuterRef("pk")).exclude(match_type=MatchType.TEMPORARY)
    if match_type != MATCH_TYPE_ALL:
        proposals = proposals.filter(match_type=match_type)
    return proposals.order_by("potential_matching_created_at")


def _first_match_queryset(match_type):
    matches = (
        Match.objects.filter(Q(user1=OuterRef("pk")) | Q(user2=OuterRef("pk")), support_matching=False)
        .exclude(match_type=MatchType.TEMPORARY)
        .order_by("created_at")
    )
    if match_type != MATCH_TYPE_ALL:
        matches = matches.filter(match_type=match_type)
    return matches


def _cohort_with_event_annotations(cohort, match_type):
    return cohort.annotate(
        first_proposal_at=Subquery(_first_proposal_queryset(match_type).values("potential_matching_created_at")[:1]),
        first_match_at=Subquery(_first_match_queryset(match_type).values("created_at")[:1]),
    )


def _collect_waiting_days_from_users(users, event_attr, earliest_prematch_end_by_user):
    now = timezone.now()
    waiting_days = []
    still_waiting_count = 0

    for user in users:
        event_at = getattr(user, event_attr, None)
        days = _waiting_days_for_user(user, event_at, now, earliest_prematch_end_by_user)
        if days is None:
            continue
        waiting_days.append(days)
        if event_at is None:
            still_waiting_count += 1

    return waiting_days, still_waiting_count


def _waiting_time_statistics(accessible_users, start_datetime, end_datetime, match_type):
    cohort, earliest_prematch_end_by_user = _onboarded_users_in_range(accessible_users, start_datetime, end_datetime)
    annotated_users = list(_cohort_with_event_annotations(cohort, match_type).iterator(chunk_size=500))

    learners = [user for user in annotated_users if user.profile.user_type == Profile.TypeChoices.LEARNER]
    volunteer_users = [user for user in annotated_users if user.profile.user_type == Profile.TypeChoices.VOLUNTEER]

    first_proposal_days, first_proposal_still_waiting = _collect_waiting_days_from_users(
        learners, "first_proposal_at", earliest_prematch_end_by_user
    )
    total_match_days, total_match_still_waiting = _collect_waiting_days_from_users(
        annotated_users, "first_match_at", earliest_prematch_end_by_user
    )
    learner_match_days, learner_match_still_waiting = _collect_waiting_days_from_users(
        learners, "first_match_at", earliest_prematch_end_by_user
    )
    volunteer_match_days, volunteer_match_still_waiting = _collect_waiting_days_from_users(
        volunteer_users, "first_match_at", earliest_prematch_end_by_user
    )

    return {
        "first_proposal_learners": _waiting_time_summary(
            first_proposal_days, first_proposal_still_waiting, cohort_count=len(learners)
        ),
        "first_match_total": _waiting_time_summary(
            total_match_days, total_match_still_waiting, cohort_count=len(annotated_users)
        ),
        "first_match_learners": _waiting_time_summary(
            learner_match_days, learner_match_still_waiting, cohort_count=len(learners)
        ),
        "first_match_volunteers": _waiting_time_summary(
            volunteer_match_days, volunteer_match_still_waiting, cohort_count=len(volunteer_users)
        ),
    }


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_proposal_statistics(request):
    today = timezone.localdate()
    default_start = today - timedelta(days=365)
    start_date = _parse_date_input(request.data.get("start_date"), default_start)
    end_date = _parse_date_input(request.data.get("end_date"), today)
    match_type = request.data.get("match_type", MATCH_TYPE_ALL)

    if match_type not in SUPPORTED_MATCH_TYPES:
        return Response({"msg": "Match proposal type not supported"}, status=400)

    start_datetime, end_datetime = _inclusive_datetime_range(start_date, end_date)
    accessible_users = _accessible_users(request.user)
    proposals = _base_proposal_queryset(accessible_users, start_datetime, end_datetime)
    proposals = _filter_proposals_by_match_type(proposals, match_type)
    summary = _proposal_outcome_summary(proposals)
    waiting_time = _waiting_time_statistics(accessible_users, start_datetime, end_datetime, match_type)
    first_proposal_outcome_waiting_time = _first_proposal_outcome_waiting_time(proposals, match_type)

    return Response(
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "match_type": match_type,
            **summary,
            "waiting_time": waiting_time,
            "first_proposal_outcome_waiting_time": first_proposal_outcome_waiting_time,
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_proposal_outcome_trend(request):
    today = timezone.localdate()
    default_start = today - timedelta(days=365)
    start_date = _parse_date_input(request.data.get("start_date"), default_start)
    end_date = _parse_date_input(request.data.get("end_date"), today)
    match_type = request.data.get("match_type", MATCH_TYPE_ALL)

    if match_type not in SUPPORTED_MATCH_TYPES:
        return Response({"msg": "Match proposal type not supported"}, status=400)

    accessible_users = _accessible_users(request.user)
    data = []

    for month_start in _iter_month_starts(start_date, end_date):
        month_end = min(_month_end(month_start), end_date)
        start_datetime, end_datetime = _inclusive_datetime_range(month_start, month_end)
        month_proposals = _base_proposal_queryset(accessible_users, start_datetime, end_datetime)
        month_proposals = _filter_proposals_by_match_type(month_proposals, match_type)
        summary = _proposal_outcome_summary(month_proposals)

        data.append(
            {
                "date": month_start.isoformat(),
                "cohort_size": summary["total_proposals"],
                **summary,
            }
        )

    return Response(data)


api_urls = [
    path("api/matching/match-proposals/statistics/", match_proposal_statistics),
    path("api/matching/match-proposals/statistics/outcome-trend/", match_proposal_outcome_trend),
]
