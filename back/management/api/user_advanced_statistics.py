from chat.models import Message
from django.utils import timezone
from datetime import date, timedelta
from management.models.unconfirmed_matches import ProposedMatch
from django.db import connection
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.urls import path
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from video.models import LivekitSession

from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS, get_match_list_by_name
from management.api.user_advanced_filter_lists import FILTER_LISTS, USER_JOURNEY_FILTER_LISTS, get_list_by_name
from management.helpers import IsAdminOrMatchingUser
from management.helpers.query_logger import QueryLogger
from management.models.matches import Match
from management.models.profile import Profile
from management.models.state import State
from management.models.user import User


@extend_schema(
    request=inline_serializer(
        name="UserStatisticsCountOverTimeRequest",
        fields={
            "bucket_size": serializers.IntegerField(default=1),
            "base_list": serializers.ChoiceField(
                choices=[entry.name for entry in FILTER_LISTS],
                default="all",
            ),
            "start_date": serializers.DateField(default="2022-01-01"),
            "end_date": serializers.DateField(default=date.today()),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def user_signups(request):
    # Validate the inputs
    today = date.today()
    bucket_size = request.data.get("bucket_size", 1)
    start_date = request.data.get("start_date", "2022-01-01")
    end_date = request.data.get("end_date", today)
    cumulative = request.query_params.get("cumulative", False)

    list_name = request.data.get("base_list", "all")
    selected_filter = next(filter(lambda entry: entry.name == list_name, FILTER_LISTS))

    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())

    queryset = selected_filter.queryset(qs=pre_filtered_users)

    if bucket_size == 1:
        trunc_func = TruncDay
    elif bucket_size == 7:
        trunc_func = TruncWeek
    elif bucket_size == 30:
        trunc_func = TruncMonth
    else:
        return Response({"msg": "Bucket size not supported. Only 1, 7, & 30 days are supported"}, status=400)

    # Calculate the count of users who joined before the start_date
    pre_start_date_count = queryset.filter(date_joined__lt=start_date).count()
    pre_start_data_count_volunteer = queryset.filter(
        date_joined__lt=start_date, profile__user_type=Profile.TypeChoices.VOLUNTEER
    ).count()

    user_counts = (
        queryset.filter(date_joined__range=[start_date, end_date])
        .annotate(bucket=trunc_func("date_joined"))
        .values("bucket")
        .annotate(count=Count("id"))
        .order_by("bucket")
    )
    volunteer_only_users = (
        queryset.filter(date_joined__range=[start_date, end_date], profile__user_type=Profile.TypeChoices.VOLUNTEER)
        .annotate(bucket=trunc_func("date_joined"))
        .values("bucket")
        .annotate(count=Count("id"))
        .order_by("bucket")
    )

    print("user_counts", user_counts)
    print("volunteer_only_users", volunteer_only_users)

    if cumulative:
        cumulative_count = pre_start_date_count
        cumulative_count_volunteer = pre_start_data_count_volunteer
        data = []
        for i, stats in enumerate(user_counts):
            cumulative_count += stats["count"]
            if i < len(volunteer_only_users):
                cumulative_count_volunteer += volunteer_only_users[i]["count"]
            data.append(
                {
                    "date": stats["bucket"],
                    "count": cumulative_count,
                    "count_ler": cumulative_count - cumulative_count_volunteer,
                    "count_vol": cumulative_count_volunteer,
                }
            )
    else:
        data = []
        for i, stats in enumerate(user_counts):
            volunteer_count = 0
            if i < len(volunteer_only_users):
                volunteer_count = volunteer_only_users[i]["count"]
            data.append(
                {
                    "date": stats["bucket"],
                    "count": stats["count"],
                    "count_ler": stats["count"] - volunteer_count,
                    "count_vol": volunteer_count,
                }
            )

    return Response(data)


@extend_schema(
    request=inline_serializer(
        name="MessageStatisticsCountOverTimeRequest",
        fields={
            "bucket_size": serializers.IntegerField(default=1),
            "base_list": serializers.ChoiceField(
                choices=[entry.name for entry in FILTER_LISTS],
                default="all",
            ),
            "start_date": serializers.DateField(default="2022-01-01"),
            "end_date": serializers.DateField(default=date.today()),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def message_statistics(request):
    # Validate the inputs
    today = date.today()
    bucket_size = request.data.get("bucket_size", 1)

    start_date = request.data.get("start_date", "2022-01-01")
    end_date = request.data.get("end_date", today)

    list_name = request.data.get("base_list", "all")
    selected_filter = next(filter(lambda entry: entry.name == list_name, FILTER_LISTS))

    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())

    queryset = selected_filter.queryset(qs=pre_filtered_users)

    if bucket_size == 1:
        trunc_func = TruncDay
    elif bucket_size == 7:
        trunc_func = TruncWeek
    elif bucket_size == 30:
        trunc_func = TruncMonth
    else:
        return Response({"msg": "Bucket size not supported only 1 & 7 days are supported"}, status=400)

    message_queryset = (
        Message.objects.filter(sender__in=queryset, recipient__in=queryset, created__range=[start_date, end_date])
        .annotate(bucket=trunc_func("created"))
        .values("bucket")
        .annotate(count=Count("id"))
        .order_by("bucket")
    )

    data = [{"date": stats["bucket"], "count": stats["count"]} for stats in message_queryset]

    return Response(data)


@extend_schema(
    request=inline_serializer(
        name="LivekitSessionStatisticsCountOverTimeRequest",
        fields={
            "bucket_size": serializers.IntegerField(default=1),
            "base_list": serializers.ChoiceField(
                choices=[entry.name for entry in FILTER_LISTS],
                default="all",
            ),
            "start_date": serializers.DateField(default="2022-01-01"),
            "end_date": serializers.DateField(default=date.today()),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def livekit_session_statistics(request):
    # Validate the inputs
    today = date.today()
    bucket_size = request.data.get("bucket_size", 1)

    min_start_date = date(2024, 4, 4)
    start_date = request.data.get("start_date", f"{min_start_date}")
    if start_date < f"{min_start_date}":
        start_date = f"{min_start_date}"

    end_date = request.data.get("end_date", today)

    list_name = request.data.get("base_list", "all")

    selected_filter = next(filter(lambda entry: entry.name == list_name, FILTER_LISTS))

    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())

    queryset = selected_filter.queryset(qs=pre_filtered_users)

    aggregation = request.query_params.get("aggregation", "count")

    if bucket_size == 1:
        trunc_func = TruncDay
    elif bucket_size == 7:
        trunc_func = TruncWeek
    elif bucket_size == 30:
        trunc_func = TruncMonth
    else:
        return Response({"msg": "Bucket size not supported only 1 & 7 days are supported"}, status=400)

    livekit_queryset = LivekitSession.objects.filter(
        u1__in=queryset, u2__in=queryset, both_have_been_active=True, created_at__range=[start_date, end_date]
    ).annotate(bucket=trunc_func("created_at"))

    if aggregation == "count":
        livekit_queryset = livekit_queryset.values("bucket").annotate(count=Count("id")).order_by("bucket")
        data = [{"date": stats["bucket"], "count": stats["count"]} for stats in livekit_queryset]
    elif aggregation == "total_time":
        livekit_queryset = (
            livekit_queryset.values("bucket")
            .annotate(total_time=Sum(F("end_time") - F("created_at")))
            .order_by("bucket")
        )
        data = [
            {"date": stats["bucket"], "count": stats["total_time"].total_seconds() / 60.0} for stats in livekit_queryset
        ]
    elif aggregation == "average_time":
        livekit_queryset = (
            livekit_queryset.values("bucket")
            .annotate(average_time=Avg(F("end_time") - F("created_at")))
            .order_by("bucket")
        )
        data = [
            {"date": stats["bucket"], "count": stats["average_time"].total_seconds() / 60.0}
            for stats in livekit_queryset
        ]
    else:
        return Response({"msg": "Aggregation type not supported."}, status=400)

    return Response(data)


def get_bucket_statistics(pre_filtered_users, selected_filters=None, filter_lists=FILTER_LISTS):
    """
    Calculate bucket statistics for a given set of users and filters.
    
    Args:
        pre_filtered_users: QuerySet of pre-filtered User objects
        selected_filters: List of filter names to apply (default: None, uses all filters)
        filter_lists: List of filter definitions to use (default: FILTER_LISTS)
    
    Returns:
        dict: Contains buckets, missing_ids, and intersecting_ids_lists
    """
    if selected_filters is None:
        selected_filters = [entry.name for entry in filter_lists]

    user_buckets = []
    selected_filters_list = []
    pre_filtered_uj_lists = {entry.name: entry for entry in filter_lists if entry.name in selected_filters}
    
    for filter_name in selected_filters:
        filter_list_entry = pre_filtered_uj_lists[filter_name]
        selected_filters_list.append(filter_list_entry)

    query_logger = QueryLogger()
    last_query_log_index = 0
    user_list_ids = {}
    all_ids_set = set()
    
    with connection.execute_wrapper(query_logger):
        for i, filter_list in enumerate(selected_filters_list):
            queryset = filter_list.queryset(qs=pre_filtered_users)
            count = queryset.count()
            duration = sum([query["duration"] for query in query_logger.queries[last_query_log_index:]])
            last_query_log_index = len(query_logger.queries) - 1
            
            user_buckets.append({
                "name": filter_list.name,
                "description": filter_list.description,
                "count": count,
                "id": i,
                "query_duration": duration,
            })

            user_list_ids[filter_list.name] = {
                "ids": queryset.values_list("id", flat=True),
            }

            if filter_list.name != "all":
                all_ids_set.update(user_list_ids[filter_list.name]["ids"])

    # Calculate intersecting IDs
    exclude_intersection_check = [
        "all",
        "needs_matching",
        "match_journey_v2__proposed_matches",
        "match_journey_v2__expired_proposals",
    ]
    
    intersecting_ids_lists = {}
    intersection_check_lists = [
        list_name for list_name in selected_filters if list_name not in exclude_intersection_check
    ]
    intersection_check_lists_not_processed = intersection_check_lists.copy()

    for list_name in intersection_check_lists:
        intersection_check_lists_not_processed.remove(list_name)
        for other_list_name in intersection_check_lists_not_processed:
            if list_name != other_list_name:
                intersecting_ids = set(user_list_ids[list_name]["ids"]).intersection(
                    user_list_ids[other_list_name]["ids"]
                )
                if len(intersecting_ids) > 0:
                    intersecting_ids_lists[f"{list_name}---{other_list_name}"] = intersecting_ids

    all_ids = set(user_list_ids["all"]["ids"])
    missing_ids = all_ids.difference(all_ids_set)

    return {
        "buckets": user_buckets,
        "missing_ids": list(missing_ids),
        "intersecting_ids_lists": intersecting_ids_lists,
    }

@extend_schema(
    request=inline_serializer(
        name="BucketStatisticsCountOverTimeRequest",
        fields={
            "selected_filters": serializers.ListField(
                child=serializers.ChoiceField(
                    choices=[entry.name for entry in USER_JOURNEY_FILTER_LISTS],
                ),
                required=True,
            ),
            "start_date": serializers.DateField(default="2021-01-01", required=False),
            "end_date": serializers.DateField(default=date.today(), required=False),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def bucket_statistics(request):
    today = date.today()
    start_date = request.data.get("start_date", "2022-01-01")
    end_date = request.data.get("end_date", today)

    # Get pre-filtered users based on permissions and date range
    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())
    pre_filtered_users = pre_filtered_users.filter(date_joined__range=[start_date, end_date])

    # Get selected filters from request
    selected_filters = request.data.get("selected_filters", None)

    # Get bucket statistics using the extracted function
    stats = get_bucket_statistics(
        pre_filtered_users=pre_filtered_users,
        selected_filters=selected_filters,
        filter_lists=FILTER_LISTS
    )

    return Response(stats)


def get_match_bucket_statistics(pre_filtered_matches, selected_filters=None, filter_lists=MATCH_JOURNEY_FILTERS):
    """
    Calculate match bucket statistics for a given set of matches and filters.
    
    Args:
        pre_filtered_matches: QuerySet of pre-filtered Match objects
        selected_filters: List of filter names to apply (default: None, uses all filters)
        filter_lists: List of filter definitions to use (default: MATCH_JOURNEY_FILTERS)
    
    Returns:
        dict: Contains buckets, missing_ids, and intersecting_ids_lists
    """
    if selected_filters is None:
        selected_filters = [entry.name for entry in filter_lists]

    if "match_journey_v2__all" not in selected_filters:
        selected_filters.append("match_journey_v2__all")

    query_logger = QueryLogger()
    last_query_log_index = 0
    all_ids_set = set()
    user_list_ids = {}

    with connection.execute_wrapper(query_logger):
        match_buckets = []
        selected_filters_list = [entry for entry in filter_lists if entry.name in selected_filters]
        
        for i, filter_list in enumerate(selected_filters_list):
            queryset = filter_list.queryset(qs=pre_filtered_matches)
            count = queryset.count()
            duration = sum([query["duration"] for query in query_logger.queries[last_query_log_index:]])
            last_query_log_index = len(query_logger.queries) - 1
            
            match_buckets.append({
                "name": filter_list.name,
                "description": filter_list.description,
                "count": count,
                "id": i,
                "query_duration": duration,
            })

            user_list_ids[filter_list.name] = {
                "ids": queryset.values_list("id", flat=True),
            }

            if filter_list.name != "match_journey_v2__all":
                all_ids_set.update(user_list_ids[filter_list.name]["ids"])

    # Calculate intersecting IDs
    exclude_intersection_check = [
        "all",
        "needs_matching",
        "match_journey_v2__all",
        "match_journey_v2__proposed_matches",
        "match_journey_v2__expired_proposals",
    ]

    intersecting_ids_lists = {}
    intersection_check_lists = [
        list_name for list_name in selected_filters if list_name not in exclude_intersection_check
    ]
    intersection_check_lists_not_processed = intersection_check_lists.copy()

    for list_name in intersection_check_lists:
        intersection_check_lists_not_processed.remove(list_name)
        for other_list_name in intersection_check_lists_not_processed:
            if list_name != other_list_name:
                intersecting_ids = set(user_list_ids[list_name]["ids"]).intersection(
                    user_list_ids[other_list_name]["ids"]
                )
                if len(intersecting_ids) > 0:
                    intersecting_ids_lists[f"{list_name}---{other_list_name}"] = intersecting_ids

    all_ids = set(user_list_ids["match_journey_v2__all"]["ids"])
    missing_ids = all_ids.difference(all_ids_set)

    return {
        "buckets": match_buckets,
        "intersecting_ids_lists": intersecting_ids_lists,
        "missing_ids": list(missing_ids),
    }

@extend_schema(
    request=inline_serializer(
        name="MatchBucketStatisticsCountOverTimeRequest",
        fields={
            "selected_filters": serializers.ListField(
                child=serializers.ChoiceField(
                    choices=[entry.name for entry in MATCH_JOURNEY_FILTERS],
                ),
                required=True,
            ),
            "start_date": serializers.DateField(default="2021-01-01", required=False),
            "end_date": serializers.DateField(default=date.today(), required=False),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_bucket_statistics(request):
    today = date.today()
    start_date = request.data.get("start_date", "2022-01-01")
    end_date = request.data.get("end_date", today)

    # Get pre-filtered users based on permissions
    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())

    # Get pre-filtered matches based on users and date range
    pre_filtered_matches = Match.objects.filter(
        Q(user1__in=pre_filtered_users) | Q(user2__in=pre_filtered_users),
        created_at__range=[start_date, end_date]
    )

    # Get selected filters from request
    selected_filters = request.data.get("selected_filters", None)

    # Get match bucket statistics using the extracted function
    stats = get_match_bucket_statistics(
        pre_filtered_matches=pre_filtered_matches,
        selected_filters=selected_filters,
        filter_lists=MATCH_JOURNEY_FILTERS
    )

    return Response(stats)


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def comany_video_call_and_matching_report(request, company):
    users = User.objects.filter(state__company=company)

    total_video_time_seconds_all_users = 0  # Variable to keep track of total video time for all users

    MAX_VIDEO_CALL_DURATION_SECONDS = 2 * 60 * 60  # 2 hours in seconds

    full_report = ""

    def report(text):
        nonlocal full_report
        full_report += text + "\n"

    for user in users:
        report(f"User: {user.username}")
        report("=" * 40)

        # Retrieve user's matches excluding support matches
        matches_as_user1 = Match.objects.filter(user1=user, support_matching=False)
        matches_as_user2 = Match.objects.filter(user2=user, support_matching=False)

        matches = matches_as_user1.union(matches_as_user2)

        report("Matches:")
        for match in matches:
            status = "Confirmed" if match.confirmed else "Pending Confirmation"
            match_user1 = match.user1.username
            match_user2 = match.user2.username
            confirmation_status = []

            if match.confirmed_by == match.user1:
                confirmation_status.append(f"{match_user1} confirmed")
            elif match.confirmed_by == match.user2:
                confirmation_status.append(f"{match_user2} confirmed")
            else:
                if match.confirmed:
                    confirmation_status.append("Both confirmed")
                else:
                    confirmation_status.append("No one confirmed")

            report(
                f"\tMatch with {match_user1 if match_user1 != user.username else match_user2} - {status} ({', '.join(confirmation_status)})"
            )

        report("=" * 20)

        # Retrieve user's video calls where both users have been active
        video_calls_as_u1 = LivekitSession.objects.filter(u1=user, both_have_been_active=True)
        video_calls_as_u2 = LivekitSession.objects.filter(u2=user, both_have_been_active=True)

        video_calls = video_calls_as_u1.union(video_calls_as_u2)

        total_video_time_seconds_user = 0  # Variable to keep track of video time for the current user

        report("Video Calls:")
        for call in video_calls:
            other_user = call.u1 if call.u1 != user else call.u2
            active_status = "Active" if call.is_active else "Inactive"

            # Calculate call duration if end time is available
            if call.end_time:
                start_time = call.created_at
                end_time = call.end_time
                duration = end_time - start_time
                if duration.total_seconds() > MAX_VIDEO_CALL_DURATION_SECONDS:
                    report(f"\tSkipping excessively long video call with {other_user.username}: Duration {duration}")
                    continue  # Skip calls longer than 2 hours
                total_video_time_seconds_user += duration.total_seconds()
                report(f"\tVideo call with {other_user.username}: Duration {duration}, Status: {active_status}")
            else:
                report(f"\tVideo call with {other_user.username}: Status: {active_status}")

        total_video_time_minutes_user = total_video_time_seconds_user / 60
        report(f"Total Video Time for {user.username}: {total_video_time_minutes_user:.2f} minutes")
        report("=" * 40)

        # Add user's video time to the global total
        total_video_time_seconds_all_users += total_video_time_seconds_user

    # Calculate total video time for all users
    total_video_time_minutes_all_users = total_video_time_seconds_all_users / 60
    report(f"Total Video Time for All Users: {total_video_time_minutes_all_users:.2f} minutes")
    total_hours = total_video_time_minutes_all_users / 60.0
    report(f"Total Video Time for All Users: {total_hours:.2f} hours")
    return Response({"report": full_report})


def user_signup_loss_statistic(start_date="2022-01-01", end_date=date.today(), caller=None):
    user_lists_required = [
        "all",
        "journey_v2__never_active",
        "journey_v2__user_created",
        "journey_v2__user_deleted",
        "journey_v2__email_verified",
        "journey_v2__user_form_completed",
        "journey_v2__too_low_german_level",
        "journey_v2__booked_onboarding_call",
        "journey_v2__no_show",
    ]

    exclude_intersection_check = ["all"]
    intersection_check_lists = [
        list_name for list_name in user_lists_required if list_name not in exclude_intersection_check
    ]

    user_list_ids = {}

    pre_filtered_users = User.objects.all()
    if not caller.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=caller.state.managed_users.all())

    pre_filtered_users = pre_filtered_users.filter(date_joined__range=[start_date, end_date])

    print(pre_filtered_users.count())

    # retrieve all the id's we need
    for list_name in user_lists_required:
        user_list = get_list_by_name(list_name)
        filtered_list_users = user_list.queryset(qs=pre_filtered_users)

        user_list_ids[list_name] = {
            "ids": filtered_list_users.values_list("id", flat=True),
            "count": filtered_list_users.count(),
        }

    # check for id's that are in multiple lists

    intersecting_ids_lists = {}

    for list_name in intersection_check_lists:
        for other_list_name in intersection_check_lists:
            if list_name != other_list_name:
                intersecting_ids = set(user_list_ids[list_name]["ids"]).intersection(
                    user_list_ids[other_list_name]["ids"]
                )
                if len(intersecting_ids) > 0:
                    intersecting_ids_lists[f"{list_name}---{other_list_name}"] = intersecting_ids

    print(intersecting_ids_lists)

    return {
        "user_list_ids": user_list_ids,
        "intersecting_ids_lists": intersecting_ids_lists,
        "exclude_intersection_check": exclude_intersection_check,
        "start_date": start_date,
        "end_date": end_date,
    }


def user_signup_loss_statistic_v2(start_date="2022-01-01", end_date=date.today(), caller=None):
    user_lists_required = [
        "all",
        "journey_v2__user_created",
        "journey_v2__email_verified",
        "journey_v2__user_form_completed",
        "journey_v2__booked_onboarding_call",
        "journey_v2__first_search",
        "journey_v2__user_searching_again",
        "journey_v2__pre_matching",
        "journey_v2__match_takeoff",
        "journey_v2__active_matching",
        "journey_v2__never_active",
        "journey_v2__no_show",
        "journey_v2__user_ghosted",
        "journey_v2__no_confirm",
        "journey_v2__happy_inactive",
        "journey_v2__too_low_german_level",
        "journey_v2__unmatched",
        "journey_v2__gave_up_searching",
        "journey_v2__user_deleted",
    ]

    exclude_intersection_check = ["all"]
    intersection_check_lists = [
        list_name for list_name in user_lists_required if list_name not in exclude_intersection_check
    ]

    user_list_ids = {}

    pre_filtered_users = User.objects.all()
    if not caller.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=caller.state.managed_users.all())

    pre_filtered_users = pre_filtered_users.filter(date_joined__range=[start_date, end_date])

    print(pre_filtered_users.count())

    # retrieve all the id's we need
    for list_name in user_lists_required:
        user_list = get_list_by_name(list_name)
        filtered_list_users = user_list.queryset(qs=pre_filtered_users)

        user_list_ids[list_name] = {
            "ids": filtered_list_users.values_list("id", flat=True),
            "count": filtered_list_users.count(),
        }

    # check for id's that are in multiple lists

    intersecting_ids_lists = {}

    for list_name in intersection_check_lists:
        for other_list_name in intersection_check_lists:
            if list_name != other_list_name:
                intersecting_ids = set(user_list_ids[list_name]["ids"]).intersection(
                    user_list_ids[other_list_name]["ids"]
                )
                if len(intersecting_ids) > 0:
                    intersecting_ids_lists[f"{list_name}---{other_list_name}"] = intersecting_ids

    print(intersecting_ids_lists)
    
    # Calculate cumulative values and percentages
    total_users = user_list_ids["all"]["count"]
    journey_steps = user_lists_required
    total_buckets = {"all": total_users}
    bucket_percentages = {"all": 100.0}
    
    remaining_users = total_users
    for step in journey_steps:
        step_count = user_list_ids[step]["count"]
        remaining_users -= step_count
        total_buckets[step] = remaining_users
        bucket_percentages[step] = (remaining_users / total_users) * 100 if total_users > 0 else 0

    return {
        "user_list_ids": user_list_ids,
        "intersecting_ids_lists": intersecting_ids_lists,
        "exclude_intersection_check": exclude_intersection_check,
        "start_date": start_date,
        "end_date": end_date,
        "total_buckets": total_buckets,
        "bucket_percentages": bucket_percentages,
        "all_summed": sum([user_list_ids[list_name]["count"] 
            for list_name in user_lists_required 
            if list_name not in exclude_intersection_check
        ]),
    }


def match_quality_statistic(start_date="2022-01-01", end_date=date.today(), caller=None):
    match_lists_required = [
        "match_journey_v2__proposed_matches",
        "match_journey_v2__unviewed",
        "match_journey_v2__one_user_viewed",
        "match_journey_v2__confirmed_no_contact",
        "match_journey_v2__confirmed_single_party_contact",
        "match_journey_v2__first_contact",
        "match_journey_v2__match_ongoing",
        "match_journey_v2__match_free_play",
        "match_journey_v2__completed_match",
        "match_journey_v2__never_confirmed",
        "match_journey_v2__no_contact",
        "match_journey_v2__user_ghosted",
        "match_journey_v2__expired_proposals",
    ]

    exclude_intersection_check = ["all"]
    intersection_check_lists = [
        list_name for list_name in match_lists_required if list_name not in exclude_intersection_check
    ]

    pre_filtered_users = User.objects.all()
    if not caller.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=caller.state.managed_users.all())

    pre_filtered_matches = Match.objects.filter(
        Q(user1__in=pre_filtered_users) | Q(user2__in=pre_filtered_users), created_at__range=[start_date, end_date]
    )

    match_list_ids = {}

    # retrieve all the id's we need
    for list_name in match_lists_required:
        match_list = get_match_list_by_name(list_name)
        filtered_list_matches = match_list.queryset(qs=pre_filtered_matches)

        match_list_ids[list_name] = {
            "ids": filtered_list_matches.values_list("id", flat=True),
            "count": filtered_list_matches.count(),
        }

    # check for id's that are in multiple lists
    for list_name in intersection_check_lists:
        for other_list_name in intersection_check_lists:
            if list_name != other_list_name:
                intersecting_ids = set(match_list_ids[list_name]["ids"]).intersection(
                    match_list_ids[other_list_name]["ids"]
                )
                if len(intersecting_ids) > 0:
                    match_list_ids[f"{list_name}---{other_list_name}"] = intersecting_ids

    return {
        "match_list_ids": match_list_ids,
        "exclude_intersection_check": exclude_intersection_check,
        "start_date": start_date,
        "end_date": end_date,
    }


@extend_schema(
    request=inline_serializer(
        name="MatchQualityStatisticsRequest",
        fields={
            "start_date": serializers.DateField(default="2022-01-01"),
            "end_date": serializers.DateField(default=date.today()),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def match_quality_statistics(request):
    start_date = request.data.get("start_date", "2022-01-01")
    end_date = request.data.get("end_date", date.today())
    caller = request.user

    return Response(match_quality_statistic(start_date, end_date, caller))


@extend_schema(
    request=inline_serializer(
        name="UserSignupLossStatisticsRequest",
        fields={
            "start_date": serializers.DateField(default="2022-01-01"),
            "end_date": serializers.DateField(default=date.today()),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def user_signup_loss_statistics(request):
    start_date = request.data.get("start_date", "2022-01-01")
    end_date = request.data.get("end_date", date.today())
    caller = request.user

    return Response(user_signup_loss_statistic_v2(start_date, end_date, caller))


# Returns the average waiting time (from prematch call to being matched) for all eligible users
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def user_match_waiting_time_statistics(request):
    start_date = request.data.get("start_date", "2024-05-01")
    end_date = request.data.get("end_date", date.today())
    caller = request.user

    # Get all eligible users who have had a pre-matching call and are currently searching
    eligible_users = User.objects.filter(
        state__had_prematching_call=True,
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__updated_at__gte=start_date,
        state__updated_at__lte=end_date,
    )

    total_waiting_time = 0
    num_users = 0

    for user in eligible_users:
        # @Simba14 'self' doesnt work here, not sure if you can directly call 'user_advanced.AvdancedUserViewset.match_waiting_time )
        # Rather I'd recommend to make a helper match_waiting_time(user)
        waiting_time = self.match_waiting_time(request, pk=user.pk).data.get("waiting_time")
        if waiting_time is not None:
            total_waiting_time += waiting_time
            num_users += 1

    if num_users > 0:
        average_waiting_time = total_waiting_time / num_users
        return Response({"average_waiting_time": average_waiting_time})
    else:
        return Response({"error": "No eligible users found within the specified date range."}, status=404)
    
@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def kpi_dashboard_statistics_signups(request):
    # All the specific statistics for the new KPI dashboard
    # - Total Registered Users
    # - Last 7 days
    # - % Volunteers
    # - sighnups last 30 days
    
    
    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())
        
    total_registered_users = pre_filtered_users.count()
    last_7_days = pre_filtered_users.filter(date_joined__range=[timezone.now() - timedelta(days=7), timezone.now()]).count()
    if last_7_days == 0:
        last_7_days = 1 # Avoid division by zero
    total_registered_volunteers_last_7_days = pre_filtered_users.filter(date_joined__range=[timezone.now() - timedelta(days=7), timezone.now()], profile__user_type=Profile.TypeChoices.VOLUNTEER).count()
    signups_last_30_days = pre_filtered_users.filter(date_joined__range=[timezone.now() - timedelta(days=30), timezone.now()]).count()
    
    bucket_statistics = get_bucket_statistics(pre_filtered_users, selected_filters=[
          'all',
          'journey_v2__never_active',
          'journey_v2__user_created',
          'journey_v2__user_deleted',
          'journey_v2__email_verified',
          'journey_v2__user_form_completed',
          'journey_v2__too_low_german_level',
          'journey_v2__booked_onboarding_call',
          'journey_v2__no_show',
    ])
    
    # Calculate bucket statistics percentages
    modified_buckets = []
    all_bucket = next(bucket for bucket in bucket_statistics['buckets'] if bucket['name'] == 'all')
    top_count = all_bucket['count']
    summed = 0

    modified_buckets.append({
        'name': 'all',
        'count': top_count,
        'raw_count': top_count - 0,
        'percentage': 100.0,
    })
    
    total = top_count
    
    for bucket in bucket_statistics['buckets']:
        if bucket['name'] != 'all':
            total -= bucket['count']
            percentage = round((total / top_count) * 100, 2)
            modified_buckets.append({
                'name': bucket['name'],
                'count': bucket['count'],
                'sub_previous': total,
                'percentage': percentage,
            })
            summed += bucket['count']

    return Response({
        "total_registered_users": total_registered_users,
        "last_7_days": last_7_days,
        "total_registered_volunteers_last_7_days": total_registered_volunteers_last_7_days,
        "percent_volunteers_last_7_days": total_registered_volunteers_last_7_days / last_7_days * 100.0,
        "signups_last_30_days": signups_last_30_days,
        "percent_onboarded_users": modified_buckets[-1]['percentage'],
    })
    
match_journey_bucket_clusters = {
    "pre-matching": [
        "match_journey_v2__proposed_matches",
        "match_journey_v2__expired_proposals",
        "match_journey_v2__unviewed",
        "match_journey_v2__one_user_viewed",
        "match_journey_v2__confirmed_no_contact",
        "match_journey_v2__confirmed_single_party_contact",
    ],
    "ongoing-matching": [
        "match_journey_v2__first_contact",
        "match_journey_v2__match_ongoing",
    ],
    "finished-matching": [
        "match_journey_v2__completed_match",
        "match_journey_v2__match_free_play",
    ],
    "failed-matching": [
        "match_journey_v2__never_confirmed",
        "match_journey_v2__no_contact",
        "match_journey_v2__user_ghosted",
        "match_journey_v2__contact_stopped",
        "match_journey_v2__reported_or_removed",
    ]
}
match_journey_exclude_sum_buckets = ["all", "match_journey_v2__proposed_matches", "match_journey_v2__expired_proposals"]

@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def kpi_dashboard_statistics_matching(request):
    # - % angenommenen Match proposals  (letzte 2-4 Wochen)
    # - % failed vs ongoing+finished Matches (total)
    # - Matches gestartet von 6 bis 12 Wochen
    
    proposals_two_weeks = ProposedMatch.objects.filter(created_at__range=[timezone.now() - timedelta(days=28), timezone.now()-timedelta(days=14)])
    accepted_proposals_two_weeks = proposals_two_weeks.filter(closed=True, rejected=False)
    accepted_proposals_two_weeks_percentage = accepted_proposals_two_weeks.count() / proposals_two_weeks.count() * 100.0
    

    return Response({
        "proposals_two_weeks": proposals_two_weeks.count(),
        "accepted_proposals_two_weeks": accepted_proposals_two_weeks.count(),
        "accepted_proposals_two_weeks_percentage": accepted_proposals_two_weeks_percentage,
    })

api_urls = [
    path("api/matching/users/statistics/signups/", user_signups),
    path("api/matching/users/statistics/messages_send/", message_statistics),
    path("api/matching/users/statistics/video_calls/", livekit_session_statistics),
    path("api/matching/users/statistics/user_journey_buckets/", bucket_statistics),
    path("api/matching/users/statistics/match_journey_buckets/", match_bucket_statistics),
    path("api/matching/users/statistics/user_signup_loss/", user_signup_loss_statistics),
    path("api/matching/users/statistics/match_quality/", match_quality_statistics),
    path("api/matching/users/statistics/user_match_waiting_time/", user_match_waiting_time_statistics),
    path("api/matching/users/statistics/kpi_singup/", kpi_dashboard_statistics_signups),
    path("api/matching/users/statistics/company_report/<str:company>/", comany_video_call_and_matching_report),
]
