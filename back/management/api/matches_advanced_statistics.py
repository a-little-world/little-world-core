import statistics
from collections import defaultdict
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

MatchRow = tuple[int, int, int, datetime]


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


def _average(values):
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _median(values):
    if not values:
        return None
    return round(statistics.median(values), 2)


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
    return Match.objects.filter(
        Q(user1__in=accessible_users) | Q(user2__in=accessible_users),
        created_at__range=[start_datetime, end_datetime],
        support_matching=False,
    ).exclude(match_type=MatchType.TEMPORARY)


def _parse_bucket_size(value):
    bucket_size = int(value)
    if bucket_size not in [1, 7, 30]:
        return None
    return bucket_size


def _pair_key(user1_id, user2_id):
    if user1_id <= user2_id:
        return user1_id, user2_id
    return user2_id, user1_id


def _collect_match_rows(matches_qs):
    return list(matches_qs.values_list("id", "user1_id", "user2_id", "created_at"))


def _user_ids_from_match_rows(match_rows):
    user_ids = set()
    for _, user1_id, user2_id, _ in match_rows:
        user_ids.add(user1_id)
        user_ids.add(user2_id)
    return user_ids


def _pair_keys_from_match_rows(match_rows):
    return {_pair_key(user1_id, user2_id) for _, user1_id, user2_id, _ in match_rows}


def _load_session_index(user_ids, pair_keys, min_created_at):
    if not user_ids:
        return {}

    sessions = LivekitSession.objects.filter(
        u1_id__in=user_ids,
        u2_id__in=user_ids,
        created_at__gte=min_created_at,
    ).values(
        "u1_id",
        "u2_id",
        "created_at",
        "both_have_been_active",
        "u1_was_active",
        "u2_was_active",
    )

    index = defaultdict(list)
    for session in sessions:
        key = _pair_key(session["u1_id"], session["u2_id"])
        if key in pair_keys:
            index[key].append(session)

    for key in index:
        index[key].sort(key=lambda session: session["created_at"])
    return index


def _load_message_direction_index(user_ids, pair_keys, min_created_at):
    if not user_ids:
        return {}

    messages = Message.objects.filter(
        sender_id__in=user_ids,
        recipient_id__in=user_ids,
        created__gte=min_created_at,
    ).values("sender_id", "recipient_id", "created")

    index = defaultdict(list)
    for message in messages:
        key = _pair_key(message["sender_id"], message["recipient_id"])
        if key in pair_keys:
            index[(message["sender_id"], message["recipient_id"])].append(message["created"])

    for key in index:
        index[key].sort()
    return index


def _activity_indices_for_matches(match_rows, min_created_at):
    user_ids = _user_ids_from_match_rows(match_rows)
    pair_keys = _pair_keys_from_match_rows(match_rows)
    return (
        _load_session_index(user_ids, pair_keys, min_created_at),
        _load_message_direction_index(user_ids, pair_keys, min_created_at),
    )


def _sessions_for_match(session_index, user1_id, user2_id, start_at, end_at=None):
    sessions = session_index.get(_pair_key(user1_id, user2_id), [])
    for session in sessions:
        created_at = session["created_at"]
        if created_at < start_at:
            continue
        if end_at is not None and created_at > end_at:
            break
        yield session


def _first_mutual_call_at(session_index, user1_id, user2_id, start_at, end_at=None):
    for session in _sessions_for_match(session_index, user1_id, user2_id, start_at, end_at=end_at):
        if session["both_have_been_active"]:
            return session["created_at"]
    return None


def _has_one_way_call(session_index, user1_id, user2_id, start_at):
    for session in _sessions_for_match(session_index, user1_id, user2_id, start_at):
        if session["both_have_been_active"]:
            return False
        if (session["u1_was_active"] and not session["u2_was_active"]) or (
            not session["u1_was_active"] and session["u2_was_active"]
        ):
            return True
    return False


def _first_message_at(message_index, sender_id, recipient_id, start_at, end_at=None):
    for created_at in message_index.get((sender_id, recipient_id), []):
        if created_at < start_at:
            continue
        if end_at is not None and created_at > end_at:
            break
        return created_at
    return None


def _messaged_in_window(message_index, sender_id, recipient_id, start_at, end_at):
    for created_at in message_index.get((sender_id, recipient_id), []):
        if created_at < start_at:
            continue
        if created_at > end_at:
            break
        return True
    return False


def _bucket_match_rows(match_rows, bucket_start, bucket_end):
    start_datetime, end_datetime = _inclusive_datetime_range(bucket_start, bucket_end)
    return [match_row for match_row in match_rows if start_datetime <= match_row[3] <= end_datetime]


def _match_cohort_trend(request, get_success_for_match, success_count_key):
    today = timezone.localdate()
    default_start = today - timedelta(days=365)
    start_date = _parse_date_input(request.data.get("start_date"), default_start)
    end_date = _parse_date_input(request.data.get("end_date"), today)
    bucket_size = _parse_bucket_size(request.data.get("bucket_size", 7))
    if bucket_size is None:
        return Response({"msg": "Bucket size not supported. Only 1, 7, & 30 days are supported"}, status=400)

    latest_mature_bucket_end = min(end_date, today - timedelta(days=14))
    if start_date > latest_mature_bucket_end:
        return Response([])

    accessible_users = _accessible_users(request.user)
    range_start_datetime, range_end_datetime = _inclusive_datetime_range(start_date, latest_mature_bucket_end)
    all_match_rows = _collect_match_rows(
        _base_match_queryset(accessible_users, range_start_datetime, range_end_datetime)
    )
    session_index, message_index = _activity_indices_for_matches(all_match_rows, range_start_datetime)

    data = []
    bucket_start = start_date

    while bucket_start <= latest_mature_bucket_end:
        bucket_end = bucket_start + timedelta(days=bucket_size - 1)
        if bucket_end > latest_mature_bucket_end:
            break

        cohort_rows = _bucket_match_rows(all_match_rows, bucket_start, bucket_end)
        cohort_size = len(cohort_rows)
        success_count = sum(
            1 for match_row in cohort_rows if get_success_for_match(match_row, session_index, message_index)
        )

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
    match_rows = _collect_match_rows(_base_match_queryset(accessible_users, start_datetime, end_datetime))
    session_index, message_index = _activity_indices_for_matches(match_rows, start_datetime)

    days_to_first_call = []
    days_to_both_messaged = []
    one_way_call_match_count = 0
    no_call_match_count = 0
    one_way_message_match_count = 0
    no_message_match_count = 0

    for _, user1_id, user2_id, created_at in match_rows:
        first_call_at = _first_mutual_call_at(session_index, user1_id, user2_id, created_at)
        if first_call_at is not None:
            days_to_first_call.append(_days_between(created_at, first_call_at))
        elif _has_one_way_call(session_index, user1_id, user2_id, created_at):
            one_way_call_match_count += 1
        else:
            no_call_match_count += 1

        first_user1_message_at = _first_message_at(message_index, user1_id, user2_id, created_at)
        first_user2_message_at = _first_message_at(message_index, user2_id, user1_id, created_at)
        if first_user1_message_at is not None and first_user2_message_at is not None:
            both_messaged_at = max(first_user1_message_at, first_user2_message_at)
            days_to_both_messaged.append(_days_between(created_at, both_messaged_at))
        elif first_user1_message_at is not None or first_user2_message_at is not None:
            one_way_message_match_count += 1
        else:
            no_message_match_count += 1

    total_matches = len(match_rows)
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
            "median_days_to_first_call": _median(days_to_first_call),
            "average_days_until_both_messaged": _average(days_to_both_messaged),
            "median_days_until_both_messaged": _median(days_to_both_messaged),
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_mutual_call_trend(request):
    def has_mutual_call_in_first_14_days(match_row, session_index, _message_index):
        _, user1_id, user2_id, created_at = match_row
        return (
            _first_mutual_call_at(
                session_index,
                user1_id,
                user2_id,
                created_at,
                end_at=created_at + timedelta(days=14),
            )
            is not None
        )

    return _match_cohort_trend(request, has_mutual_call_in_first_14_days, "mutual_call_match_count")


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_both_messaged_trend(request):
    def has_messages_both_ways_in_first_14_days(match_row, _session_index, message_index):
        _, user1_id, user2_id, created_at = match_row
        first_14_days_end = created_at + timedelta(days=14)
        return _messaged_in_window(
            message_index,
            user1_id,
            user2_id,
            created_at,
            first_14_days_end,
        ) and _messaged_in_window(
            message_index,
            user2_id,
            user1_id,
            created_at,
            first_14_days_end,
        )

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
    match_rows = _collect_match_rows(_base_match_queryset(accessible_users, start_datetime, end_datetime))
    session_index, _ = _activity_indices_for_matches(match_rows, start_datetime)
    now = timezone.now()

    data = []
    for week in range(1, 11):
        latest_match_created_at = now - timedelta(days=week * 7)
        week_start_offset = timedelta(days=(week - 1) * 7)
        week_end_offset = timedelta(days=week * 7)
        cohort_size = 0
        matches_with_call_count = 0

        for _, user1_id, user2_id, created_at in match_rows:
            if created_at > latest_match_created_at:
                continue

            cohort_size += 1
            week_start = created_at + week_start_offset
            week_end = created_at + week_end_offset
            if _first_mutual_call_at(session_index, user1_id, user2_id, week_start, end_at=week_end) is not None:
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
