import calendar
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from management.helpers import IsAdminOrMatchingUser
from management.models.unconfirmed_matches import MatchType, ProposedMatch
from management.models.user import User

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
    proposals = _base_proposal_queryset(_accessible_users(request.user), start_datetime, end_datetime)
    proposals = _filter_proposals_by_match_type(proposals, match_type)
    summary = _proposal_outcome_summary(proposals)

    return Response(
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "match_type": match_type,
            **summary,
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
