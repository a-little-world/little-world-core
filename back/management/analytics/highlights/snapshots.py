"""Highlights snapshot composed from canonical domain analytics."""

from datetime import date, datetime

from django.db.models import Q, QuerySet

from management.analytics.core import display_time
from management.analytics.match_journey.cohorts import MatchPartitionCohort
from management.analytics.registry import get_catalog_entry
from management.analytics.time_series.queries import user_messages, video_call_duration
from management.analytics.user_journey.cohorts import SignupCohort
from management.match_success import successful_matches
from management.models.matches import Match
from management.models.profile import Profile
from management.models.unconfirmed_matches import MatchType, ProposedMatch


def _sum_aggregates(aggregates) -> tuple[float, int]:
    return (
        sum(item.total for item in aggregates.values()),
        sum(item.count for item in aggregates.values()),
    )


def build_highlights_snapshot(
    accessible_users: QuerySet,
    *,
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    as_of: datetime | None = None,
) -> dict:
    """Build one internally consistent snapshot for the selected date range.

    Registrations are a signup-date cohort. Onboarding is cumulative stage reach over
    that cohort. Matches are a non-support Standard/Random Call creation cohort.
    In-flight and successful match counts use the V5 catalog and active success version.
    Calls and messages reuse the same occurrence queries as the ranged graph.
    """
    as_of = as_of or display_time.now()

    signup_cohort = SignupCohort(start_date=start_date, end_date=end_date).apply(accessible_users)
    registrations = signup_cohort.count()
    registered_volunteers = signup_cohort.filter(profile__user_type=Profile.TypeChoices.VOLUNTEER).count()
    registered_learners = signup_cohort.filter(profile__user_type=Profile.TypeChoices.LEARNER).count()

    onboarded = get_catalog_entry("funnel__onboarded").build(signup_cohort, as_of=as_of)
    onboarded_volunteers = onboarded.filter(profile__user_type=Profile.TypeChoices.VOLUNTEER).count()
    onboarded_learners = onboarded.filter(profile__user_type=Profile.TypeChoices.LEARNER).count()

    start_at, end_at = display_time.inclusive_range(start_date, end_date)
    accessible_user_ids = accessible_users.values("id")
    match_proposals_made = (
        ProposedMatch.objects.filter(
            Q(user1__in=accessible_user_ids) | Q(user2__in=accessible_user_ids),
            potential_matching_created_at__range=(start_at, end_at),
        )
        .exclude(match_type=MatchType.TEMPORARY)
        .count()
    )

    accessible_matches = Match.objects.filter(Q(user1__in=accessible_user_ids) | Q(user2__in=accessible_user_ids))
    match_cohort = MatchPartitionCohort(start_date=start_date, end_date=end_date).apply(accessible_matches)
    new_matches = match_cohort.count()
    in_flight_matches = get_catalog_entry("match_state__in_flight").build(match_cohort, as_of=as_of).count()
    successful_match_count = successful_matches(match_cohort).count()

    call_duration_by_day = video_call_duration(
        accessible_users,
        start_date=start_date,
        end_date=end_date,
        bucket_size=1,
        call_type="all",
    )
    total_video_duration_seconds, completed_video_calls = _sum_aggregates(call_duration_by_day)

    messages_by_day = user_messages(
        accessible_users,
        start_date=start_date,
        end_date=end_date,
        bucket_size=1,
        call_type="all",
    )
    messages_sent = int(_sum_aggregates(messages_by_day)[0])

    return {
        "start_date": display_time.as_display_date(start_date),
        "end_date": display_time.as_display_date(end_date),
        "registrations": registrations,
        "registered_volunteers": registered_volunteers,
        "registered_learners": registered_learners,
        "onboarded_volunteers": onboarded_volunteers,
        "onboarded_learners": onboarded_learners,
        "match_proposals_made": match_proposals_made,
        "new_matches": new_matches,
        "in_flight_matches": in_flight_matches,
        "successful_matches": successful_match_count,
        "completed_video_calls_both_active": completed_video_calls,
        "video_call_duration_seconds_both_active": round(total_video_duration_seconds, 2),
        "messages_sent_excluding_support": messages_sent,
    }
