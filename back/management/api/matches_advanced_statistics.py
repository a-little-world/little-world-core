from datetime import date, datetime, time, timedelta

from chat.models import Message
from django.db.models import Q
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from video.models import LivekitSession

from management.helpers import IsAdminOrMatchingUser
from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType
from management.models.user import User


def _parse_date_input(value, default):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return default
    return datetime.strptime(value, "%Y-%m-%d").date()


def _inclusive_datetime_range(start_date, end_date):
    return datetime.combine(start_date, time.min), datetime.combine(end_date, time.max)


def _average(values):
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _days_between(start, end):
    return round((end - start).total_seconds() / 86400, 2)


def _percentage(count, total):
    if total == 0:
        return 0
    return round(count / total * 100, 2)


def _accessible_users(user):
    users = User.objects.all()
    if not user.is_staff:
        users = users.filter(id__in=user.managed_users_queryset(active_only=False).values("id"))
    return users


def _base_match_queryset(accessible_users, start_datetime, end_datetime):
    return (
        Match.objects.filter(
            Q(user1__in=accessible_users) | Q(user2__in=accessible_users),
            created_at__range=[start_datetime, end_datetime],
            support_matching=False,
        )
        .exclude(match_type=MatchType.TEMPORARY)
        .select_related("user1", "user2")
    )


def _parse_bucket_size(value):
    bucket_size = int(value)
    if bucket_size not in [1, 7, 30]:
        return None
    return bucket_size


def _match_cohort_trend(request, get_success_for_match, success_count_key):
    today = timezone.localdate()
    default_start = today - timedelta(days=365)
    start_date = _parse_date_input(request.data.get("start_date"), default_start)
    end_date = _parse_date_input(request.data.get("end_date"), today)
    bucket_size = _parse_bucket_size(request.data.get("bucket_size", 7))
    if bucket_size is None:
        return Response({"msg": "Bucket size not supported. Only 1, 7, & 30 days are supported"}, status=400)

    # Each cohort needs a full 14-day observation window before it is included in the trend.
    latest_mature_bucket_end = min(end_date, today - timedelta(days=14))
    if start_date > latest_mature_bucket_end:
        return Response([])

    accessible_users = _accessible_users(request.user)
    data = []
    bucket_start = start_date

    while bucket_start <= latest_mature_bucket_end:
        bucket_end = bucket_start + timedelta(days=bucket_size - 1)
        if bucket_end > latest_mature_bucket_end:
            break

        start_datetime, end_datetime = _inclusive_datetime_range(bucket_start, bucket_end)
        cohort_matches = _base_match_queryset(accessible_users, start_datetime, end_datetime)

        cohort_size = cohort_matches.count()
        success_count = 0

        for match in cohort_matches.iterator(chunk_size=500):
            if get_success_for_match(match):
                success_count += 1

        data.append(
            {
                "date": bucket_start.isoformat(),
                "count": _percentage(success_count, cohort_size),
                "cohort_size": cohort_size,
                success_count_key: success_count,
            }
        )
        bucket_start = bucket_end + timedelta(days=1)

    return Response(data)


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_timing_statistics(request):
    today = date.today()
    default_start = today - timedelta(days=365)
    start_date = _parse_date_input(request.data.get("start_date"), default_start)
    end_date = _parse_date_input(request.data.get("end_date"), today)
    start_datetime, end_datetime = _inclusive_datetime_range(start_date, end_date)

    accessible_users = _accessible_users(request.user)
    matches = _base_match_queryset(accessible_users, start_datetime, end_datetime)

    days_to_first_call = []
    days_to_both_messaged = []
    one_way_call_match_count = 0
    no_call_match_count = 0
    one_way_message_match_count = 0
    no_message_match_count = 0

    for match in matches.iterator(chunk_size=500):
        pair_q = Q(u1=match.user1, u2=match.user2) | Q(u1=match.user2, u2=match.user1)
        first_call_at = (
            LivekitSession.objects.filter(pair_q, both_have_been_active=True, created_at__gte=match.created_at)
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        if first_call_at is not None:
            days_to_first_call.append(_days_between(match.created_at, first_call_at))
        else:
            one_way_call_exists = (
                LivekitSession.objects.filter(
                    pair_q,
                    created_at__gte=match.created_at,
                    both_have_been_active=False,
                )
                .filter(Q(u1_was_active=True, u2_was_active=False) | Q(u1_was_active=False, u2_was_active=True))
                .exists()
            )
            if one_way_call_exists:
                one_way_call_match_count += 1
            else:
                no_call_match_count += 1

        first_user1_message_at = (
            Message.objects.filter(sender=match.user1, recipient=match.user2, created__gte=match.created_at)
            .order_by("created")
            .values_list("created", flat=True)
            .first()
        )
        first_user2_message_at = (
            Message.objects.filter(sender=match.user2, recipient=match.user1, created__gte=match.created_at)
            .order_by("created")
            .values_list("created", flat=True)
            .first()
        )
        if first_user1_message_at is not None and first_user2_message_at is not None:
            both_messaged_at = max(first_user1_message_at, first_user2_message_at)
            days_to_both_messaged.append(_days_between(match.created_at, both_messaged_at))
        elif first_user1_message_at is not None or first_user2_message_at is not None:
            one_way_message_match_count += 1
        else:
            no_message_match_count += 1

    total_matches = matches.count()
    first_call_match_count = len(days_to_first_call)
    both_messaged_match_count = len(days_to_both_messaged)

    return Response(
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_matches": total_matches,
            "first_call_match_count": first_call_match_count,
            "first_call_match_percentage": _percentage(first_call_match_count, total_matches),
            "one_way_call_match_count": one_way_call_match_count,
            "one_way_call_match_percentage": _percentage(one_way_call_match_count, total_matches),
            "no_call_match_count": no_call_match_count,
            "no_call_match_percentage": _percentage(no_call_match_count, total_matches),
            "both_messaged_match_count": both_messaged_match_count,
            "both_messaged_match_percentage": _percentage(both_messaged_match_count, total_matches),
            "one_way_message_match_count": one_way_message_match_count,
            "one_way_message_match_percentage": _percentage(one_way_message_match_count, total_matches),
            "no_message_match_count": no_message_match_count,
            "no_message_match_percentage": _percentage(no_message_match_count, total_matches),
            "average_days_to_first_call": _average(days_to_first_call),
            "average_days_until_both_messaged": _average(days_to_both_messaged),
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_mutual_call_trend(request):
    def has_mutual_call_in_first_14_days(match):
        pair_q = Q(u1=match.user1, u2=match.user2) | Q(u1=match.user2, u2=match.user1)
        return LivekitSession.objects.filter(
            pair_q,
            both_have_been_active=True,
            created_at__gte=match.created_at,
            created_at__lte=match.created_at + timedelta(days=14),
        ).exists()

    return _match_cohort_trend(request, has_mutual_call_in_first_14_days, "mutual_call_match_count")


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_both_messaged_trend(request):
    def has_messages_both_ways_in_first_14_days(match):
        first_14_days_end = match.created_at + timedelta(days=14)
        user1_messaged = Message.objects.filter(
            sender=match.user1,
            recipient=match.user2,
            created__gte=match.created_at,
            created__lte=first_14_days_end,
        ).exists()
        user2_messaged = Message.objects.filter(
            sender=match.user2,
            recipient=match.user1,
            created__gte=match.created_at,
            created__lte=first_14_days_end,
        ).exists()
        return user1_messaged and user2_messaged

    return _match_cohort_trend(
        request,
        has_messages_both_ways_in_first_14_days,
        "both_messaged_match_count",
    )


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_video_call_week_evolution(request):
    today = timezone.localdate()
    default_start = today - timedelta(days=365)
    start_date = _parse_date_input(request.data.get("start_date"), default_start)
    end_date = _parse_date_input(request.data.get("end_date"), today)
    start_datetime, end_datetime = _inclusive_datetime_range(start_date, end_date)

    accessible_users = _accessible_users(request.user)
    matches = _base_match_queryset(accessible_users, start_datetime, end_datetime)
    data = []

    for week in range(1, 11):
        # Only include matches old enough to have completed this relative match week.
        latest_match_created_at = timezone.now() - timedelta(days=week * 7)
        week_matches = matches.filter(created_at__lte=latest_match_created_at)
        cohort_size = week_matches.count()
        matches_with_call_count = 0
        week_start_offset = timedelta(days=(week - 1) * 7)
        week_end_offset = timedelta(days=week * 7)

        for match in week_matches.iterator(chunk_size=500):
            pair_q = Q(u1=match.user1, u2=match.user2) | Q(u1=match.user2, u2=match.user1)
            had_both_active_call_in_week = LivekitSession.objects.filter(
                pair_q,
                both_have_been_active=True,
                created_at__gte=match.created_at + week_start_offset,
                created_at__lt=match.created_at + week_end_offset,
            ).exists()

            if had_both_active_call_in_week:
                matches_with_call_count += 1

        data.append(
            {
                "date": f"Week {week}",
                "count": _percentage(matches_with_call_count, cohort_size),
                "cohort_size": cohort_size,
                "matches_with_call_count": matches_with_call_count,
            }
        )

    return Response(data)


api_urls = [
    path("api/matching/matches/statistics/timing/", match_timing_statistics),
    path("api/matching/matches/statistics/mutual-call-trend/", match_mutual_call_trend),
    path("api/matching/matches/statistics/both-messaged-trend/", match_both_messaged_trend),
    path("api/matching/matches/statistics/video-call-week-evolution/", match_video_call_week_evolution),
]
