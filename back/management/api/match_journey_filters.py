# Helper function to calculate days ago
from datetime import timedelta

from chat.models import Message
from django.db.models import (
    Count,
    DateTimeField,
    DurationField,
    Exists,
    ExpressionWrapper,
    F,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Coalesce, ExtractDay, Greatest
from django.utils import timezone
from video.models import LivekitSession

from management.models.matches import Match
from management.models.unconfirmed_matches import ProposedMatch


def days_ago(days):
    return timezone.now() - timedelta(days=days)


# Per-Matching States Filters
DESIRED_MATCH_DURATION_WEEKS = 10
LAST_INTERACTION_DAYS = 21
DAYS_UNTILL_GHOSTED = 21
NEVER_CONFIRMED_DAYS = 10

def only_non_support_matching(qs=Match.objects.all()):
    return qs.filter(support_matching=False)


def match_unviewed(qs=Match.objects.all(), mutal_ghosted_days=DAYS_UNTILL_GHOSTED):
    """
    1. Match Unviewed
    Filters matches that are active and not yet confirmed by both users.
    """
    return qs.filter(
        active=True,
        support_matching=False,
        confirmed=False,
        confirmed_by__isnull=True,  # No one ever confirmed this match yet
        created_at__gt=days_ago(mutal_ghosted_days),
    ).distinct()


def match_one_user_viewed(qs=Match.objects.all(), ghosted_days=NEVER_CONFIRMED_DAYS):
    """
    2. Match One User Viewed
    Filters matches that are active, not yet confirmed by both users, but confirmed by at least one user.
    """
    return qs.filter(
        active=True,
        support_matching=False,
        confirmed=False,
        confirmed_by__isnull=False,
        created_at__gt=days_ago(ghosted_days),
    ).distinct()


def all_matches(qs=Match.objects.all()):
    return qs.filter(support_matching=False)


def match_confirmed_no_contact(qs=Match.objects.all(), mutal_ghosted_days=DAYS_UNTILL_GHOSTED):
    """
    3. Match Confirmed No Contact
    Filters matches that are active, confirmed by both users, no unmatch reports, and neither user has sent messages or participated in video calls at all.
    """

    return qs.filter(
        active=True,
        support_matching=False,
        confirmed=True,
        created_at__gt=days_ago(mutal_ghosted_days),
        total_messages_counter=0,
        total_mutal_video_calls_counter=0,
    )


def match_confirmed_single_party_contact(qs=Match.objects.all(), mutal_ghosted_days=DAYS_UNTILL_GHOSTED):
    """
    4. Match Confirmed Single Party Contact
    Filters matches that are active, confirmed by both users, no unmatch reports,
    and only one user has sent messages or participated in video calls. The bot should not have
    been active in those matches.
    """

    user1_to_user2_message_exists = Message.objects.filter(sender=OuterRef("user1"), recipient=OuterRef("user2"))

    user2_to_user1_message_exists = Message.objects.filter(sender=OuterRef("user2"), recipient=OuterRef("user1"))

    return qs.filter(
        active=True, support_matching=False, confirmed=True, created_at__gt=days_ago(mutal_ghosted_days)
    ).filter(
        Q(Exists(user1_to_user2_message_exists) & ~Exists(user2_to_user1_message_exists))
        | Q(~Exists(user1_to_user2_message_exists) & Exists(user2_to_user1_message_exists))
    )


def match_first_contact(
    qs=Match.objects.all(),
):
    """
    5. Match First Contact
    Filters matches where both users have either participated in the same video call or sent at least one message to each other.
    """

    user1_to_user2_message_exists = Message.objects.filter(sender=OuterRef("user1"), recipient=OuterRef("user2"))

    user2_to_user1_message_exists = Message.objects.filter(sender=OuterRef("user2"), recipient=OuterRef("user1"))

    return qs.filter(
        active=True,
        total_messages_counter__gte=2,
        total_mutal_video_calls_counter=0,
        support_matching=False,
        confirmed=True,
        latest_interaction_at__gte=days_ago(DAYS_UNTILL_GHOSTED),
    ).filter(Q(Exists(user1_to_user2_message_exists) & Exists(user2_to_user1_message_exists)))


def match_ongoing(
    qs=Match.objects.all(),
    last_interaction_days=LAST_INTERACTION_DAYS,
    min_total_mutual_messages=2,
    min_total_mutual_video_calls=1,
    min_total_recent_mutual_messages=1,
    min_total_recent_mutual_video_calls=0,
    only_consider_last_10_weeks_matches=True,
):
    """
    6. Match Ongoing
    Filters matches where users have exchanged multiple messages or video calls,
    their last message or video call is less than 14 days ago, and the match isn't older than DESIRED_MATCH_DURATION_WEEKS.
    """
    qs = qs.filter(
        support_matching=False,
        active=True,
        latest_interaction_at__gte=days_ago(last_interaction_days),
        total_messages_counter__gte=min_total_mutual_messages,
        total_mutal_video_calls_counter__gte=min_total_mutual_video_calls,
    )

    if only_consider_last_10_weeks_matches:
        # Rename to 'less than 10 weeks old'
        qs = qs.filter(created_at__gte=days_ago(DESIRED_MATCH_DURATION_WEEKS * 7))

    return qs


def match_free_play(qs=Match.objects.all(), **kwargs):
    ## Like match ongoing but for matches older than 10 weeks
    return match_ongoing(
        qs, last_interaction_days=LAST_INTERACTION_DAYS, only_consider_last_10_weeks_matches=False, **kwargs
    ).filter(created_at__lt=days_ago(DESIRED_MATCH_DURATION_WEEKS * 7))


def completed_match(
    qs=Match.objects.all(),
    min_total_mutual_messages=2,
    min_total_mutual_video_calls=1,
    last_interaction_days=LAST_INTERACTION_DAYS,
    last_and_first_interaction_days=4 * 7,
):
    """
    8. Completed Match
    Filters matches that are over 10 weeks old, inactive, still in contact, and exchanged desired_x_messages and desired_x_video_calls.
    """
    user1_to_user2_message_exists = Message.objects.filter(sender=OuterRef("user1"), recipient=OuterRef("user2"))
    user2_to_user1_message_exists = Message.objects.filter(sender=OuterRef("user2"), recipient=OuterRef("user1"))
    
    # Now we also consider matches manually marked as 'completed' or 'completed_off_plattform'
    completed_or_completed_off_plattform = Match.objects.filter(
        Q(completed=True) | Q(completed_off_plattform=True)
    )

    now = timezone.now()
    completed_by_criteria = (
        qs.filter(
            Q(Exists(user1_to_user2_message_exists) & Exists(user2_to_user1_message_exists)),
            active=True,
            support_matching=False,
            total_messages_counter__gte=min_total_mutual_messages,
            total_mutal_video_calls_counter__gte=min_total_mutual_video_calls,
        )
        .annotate(
            duration_since_last_interaction_in_days=ExpressionWrapper(
                Greatest(ExtractDay(now - F("latest_interaction_at")), 0), output_field=DurationField()
            ),
            duration_between_first_and_last_interaction_days=ExpressionWrapper(
                Greatest(ExtractDay(F("latest_interaction_at") - F("created_at")), 0), output_field=DurationField()
            ),
        )
        .filter(
            duration_between_first_and_last_interaction_days__gte=last_and_first_interaction_days,
            duration_since_last_interaction_in_days__gte=last_interaction_days,
        )
    )
    
    return qs.filter(
        Q(id__in=completed_or_completed_off_plattform.values_list('id', flat=True)) |
        Q(id__in=completed_by_criteria.values_list('id', flat=True))
    ).annotate(
        duration_since_last_interaction_in_days=ExpressionWrapper(
            Greatest(ExtractDay(now - F("latest_interaction_at")), 0), output_field=DurationField()
        ),
        duration_between_first_and_last_interaction_days=ExpressionWrapper(
            Greatest(ExtractDay(F("latest_interaction_at") - F("created_at")), 0), output_field=DurationField()
        ),
    )

def never_confirmed(qs=Match.objects.all()):
    """
    9. Never Confirmed
    Filters matches older than a specified number of days but still unconfirmed.
    """
    return qs.filter(active=True, support_matching=False, confirmed=False, created_at__lt=days_ago(NEVER_CONFIRMED_DAYS))


def no_contact(qs=Match.objects.all()):
    """
    10. No Contact
    Filters matches that are confirmed but no contact and older than a specified number of days.
    """
    return qs.filter(
        active=True, support_matching=False, confirmed=True, created_at__lt=days_ago(LAST_INTERACTION_DAYS)
    ).filter(total_messages_counter=0, total_mutal_video_calls_counter=0)


def user_ghosted(
    qs=Match.objects.all(),
):
    """
    11. User Ghosted
    Filters matches that are confirmed, have a single party contact, and are older than a specified number of days.
    """

    user1_to_user2_message_exists = Message.objects.filter(sender=OuterRef("user1"), recipient=OuterRef("user2"))

    user2_to_user1_message_exists = Message.objects.filter(sender=OuterRef("user2"), recipient=OuterRef("user1"))

    return qs.filter(
        active=True, support_matching=False, confirmed=True, created_at__lt=days_ago(DAYS_UNTILL_GHOSTED)
    ).filter(
        Q(Exists(user1_to_user2_message_exists) & ~Exists(user2_to_user1_message_exists))
        | Q(~Exists(user1_to_user2_message_exists) & Exists(user2_to_user1_message_exists))
    )


def contact_stopped(qs=Match.objects.all()):
    ## Basicly like a completed match, but the first and last interaction times are lass than 6 weeks appart
    qs = completed_match(qs, last_and_first_interaction_days=0).filter(
        duration_between_first_and_last_interaction_days__lt=4 * 7
    )
    return qs


def matching_proposals(qs=ProposedMatch.objects.all()):
    qs = ProposedMatch.objects.all().filter(
        closed=False,
        expires_at__gte=timezone.now(),
    )
    return qs


def expired_matching_proposals(qs=ProposedMatch.objects.all()):
    qs = ProposedMatch.objects.all().filter(
        closed=True,
        expires_at__lte=timezone.now(),
    )
    return qs


def reported_or_removed_match(qs=Match.objects.all()):
    return qs.filter(
        support_matching=False,
        active=False,
    )


def sucess_matches(qs=Match.objects.all()):
    completed_matches = completed_match(qs)
    free_play_matches = match_free_play(qs)
    return completed_matches | free_play_matches

def ongoing_matches(qs=Match.objects.all()):
    first_contact_matches = match_first_contact(qs)
    ongoing_matches = match_ongoing(qs)
    return first_contact_matches | ongoing_matches

def failed_matches(qs=Match.objects.all()):
    never_confirmed_matches = never_confirmed(qs)
    no_contact_matches = no_contact(qs)
    user_ghosted_matches = user_ghosted(qs)
    return never_confirmed_matches | no_contact_matches | user_ghosted_matches
