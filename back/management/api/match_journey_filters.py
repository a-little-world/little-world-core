from django.db.models import Q, Count, F
from management.models.matches import Match
from django.db.models import ExpressionWrapper, DurationField, F, Max

# Helper function to calculate days ago
from datetime import timedelta
from django.db.models import ExpressionWrapper, DateTimeField
from django.db.models.functions import Greatest, ExtractDay
from django.utils import timezone
from django.db.models import Exists, OuterRef, Subquery
from django.db.models.functions import Coalesce
from video.models import LivekitSession
from chat.models import Message
from management.models.unconfirmed_matches import ProposedMatch


def days_ago(days):
    return timezone.now() - timedelta(days=days)


# Per-Matching States Filters
DESIRED_MATCH_DURATION_WEEKS = 10
LAST_INTERACTION_DAYS = 21
DAYS_UNTILL_GHOSTED = 14


def match_unviewed(qs=Match.objects.all(), mutal_ghosted_days=DAYS_UNTILL_GHOSTED):
    """
    1. Match Unviewed
    Filters matches that are active and not yet confirmed by both users.
    """
    return qs.filter(
        support_matching=False,  # generally remove support matches if they are 'unviewed' user has prob not finished sign-up
        confirmed=False,
        created_at__lt=days_ago(mutal_ghosted_days),
    ).distinct()


def match_one_user_viewed(qs=Match.objects.all(), ghosted_days=DAYS_UNTILL_GHOSTED):
    """
    2. Match One User Viewed
    Filters matches that are active, not yet confirmed by both users, but confirmed by at least one user.
    """
    # TODO: means one of the users only has been ghosted, we could notify that one and ask to give him a new match
    return qs.filter(support_matching=False, confirmed=False, confirmed_by__isnull=False, created_at__lt=days_ago(ghosted_days)).distinct()


def match_confirmed_no_contact(qs=Match.objects.all(), mutal_ghosted_days=DAYS_UNTILL_GHOSTED):
    """
    3. Match Confirmed No Contact
    Filters matches that are active, confirmed by both users, no unmatch reports, and neither user has sent messages or participated in video calls at all.
    """
    days_threshold = days_ago(mutal_ghosted_days)

    # Check if there is at least one message sent from user1 to user2
    user1_to_user2_message_exists = Message.objects.filter(
        sender=OuterRef('user1'),
        recipient=OuterRef('user2')
    )

    # Check if there is at least one message sent from user2 to user1
    user2_to_user1_message_exists = Message.objects.filter(
        sender=OuterRef('user2'),
        recipient=OuterRef('user1')
    )

    # Check if there's a video call either from user1 or user2
    video_call_exists = LivekitSession.objects.filter(
        Q(u1=OuterRef('user1'), u2=OuterRef('user2')) |
        Q(u1=OuterRef('user2'), u2=OuterRef('user1'))
    )

    return qs.filter(
        support_matching=False,
        confirmed=True,
        created_at__lt=days_threshold,
    ).annotate(
        user1_to_user2_message_exists_flag=Exists(user1_to_user2_message_exists),
        user2_to_user1_message_exists_flag=Exists(user2_to_user1_message_exists),
        video_call_exists_flag=Exists(video_call_exists),
    ).filter(
        user1_to_user2_message_exists_flag=False,
        user2_to_user1_message_exists_flag=False,
        video_call_exists_flag=False
    )

def match_confirmed_single_party_contact(qs=Match.objects.all(), mutal_ghosted_days=DAYS_UNTILL_GHOSTED):
    """
    4. Match Confirmed Single Party Contact
    Filters matches that are active, confirmed by both users, no unmatch reports,
    and only one user has sent messages or participated in video calls. The bot should not have 
    been active in those matches.
    """
    days_threshold = days_ago(mutal_ghosted_days)

    # Check if there is at least one message sent from user1 to user2
    user1_to_user2_message_exists = Message.objects.filter(
        sender=OuterRef('user1'),
        recipient=OuterRef('user2')
    )

    # Check if there is at least one message sent from user2 to user1
    user2_to_user1_message_exists = Message.objects.filter(
        sender=OuterRef('user2'),
        recipient=OuterRef('user1')
    )

    # Check if there's a video call either from user1 or user2
    video_call_exists = LivekitSession.objects.filter(
        Q(u1=OuterRef('user1'), u2=OuterRef('user2')) |
        Q(u1=OuterRef('user2'), u2=OuterRef('user1')),
       both_have_been_active=True, 
    )

    return qs.filter(
        support_matching=False,
        confirmed=True,
        created_at__lt=days_threshold,
    ).annotate(
        user1_to_user2_message_exists_flag=Exists(user1_to_user2_message_exists),
        user2_to_user1_message_exists_flag=Exists(user2_to_user1_message_exists),
        video_call_exists_flag=Exists(video_call_exists),
    ).filter(
        (
            Q(user1_to_user2_message_exists_flag=True, user2_to_user1_message_exists_flag=False) |
            Q(user1_to_user2_message_exists_flag=False, user2_to_user1_message_exists_flag=True)
        ) &
        Q(video_call_exists_flag=False)
    )

def match_first_contact(
        qs=Match.objects.all(), 
        min_mutual_messages=2
    ):
    """
    5. Match First Contact
    Filters matches where both users have either participated in the same video call or sent at least one message to each other.
    """
    
    # Check if there is at least one message sent from user1 to user2
    user1_to_user2_message_exists = Message.objects.filter(
        sender=OuterRef('user1'),
        recipient=OuterRef('user2')
    )

    # Check if there is at least one message sent from user2 to user1
    user2_to_user1_message_exists = Message.objects.filter(
        sender=OuterRef('user2'),
        recipient=OuterRef('user1')
    )

    # Check if both users have participated in a video call
    video_call_exists = LivekitSession.objects.filter(
        Q(both_have_been_active=True) & 
        (Q(u1=OuterRef('user1'), u2=OuterRef('user2')) | Q(u1=OuterRef('user2'), u2=OuterRef('user1')))
    )

    return qs.filter(
        (Exists(user1_to_user2_message_exists) & Exists(user2_to_user1_message_exists)) | Exists(video_call_exists),
        support_matching=False,
        confirmed=True
    )

def match_ongoing(
    qs=Match.objects.all(), 
    last_interaction_days=LAST_INTERACTION_DAYS, 
    min_total_mutual_messages=2, 
    min_total_mutual_video_calls=1, 
    min_total_recent_mutual_messages=1, 
    min_total_recent_mutual_video_calls=1,
    only_consider_last_10_weeks_matches=True
):
    """
    6. Match Ongoing
    Filters matches where users have exchanged multiple messages or video calls,
    their last message or video call is less than 14 days ago, and the match isn't older than DESIRED_MATCH_DURATION_WEEKS.
    """
    qs = (
        qs.filter(
            support_matching=False,
            confirmed=True,
        )
        .annotate(
            u1_messages=Count("user1__message_sender", filter=Q(user1__message_sender__recipient=F("user2"))),
            u2_messages=Count("user2__message_sender", filter=Q(user2__message_sender__recipient=F("user1"))),
            recent_messages_u1=Count("user1__message_sender", filter=Q(user1__message_sender__recipient=F("user2"), user1__message_sender__created__gte=days_ago(last_interaction_days))),
            recent_messages_u2=Count("user2__message_sender", filter=Q(user2__message_sender__recipient=F("user1"), user2__message_sender__created__gte=days_ago(last_interaction_days))),
            both_active_calls=Count("user1__u1_livekit_session", filter=Q(user1__u1_livekit_session__both_have_been_active=True)),
            recent_both_active_calls=Count("user1__u1_livekit_session", filter=Q(user1__u1_livekit_session__both_have_been_active=True, user1__u1_livekit_session__end_time__gte=days_ago(last_interaction_days))),
        )
        .annotate(
            mutual_messages=F("u1_messages") + F("u2_messages"),
            recent_mutual_messages=F("recent_messages_u1") + F("recent_messages_u2"),
        )
        .filter(mutual_messages__gte=min_total_mutual_messages, both_active_calls__gte=min_total_mutual_video_calls, recent_mutual_messages__gte=min_total_recent_mutual_messages, recent_both_active_calls__gte=min_total_recent_mutual_video_calls)
    )
    
    if only_consider_last_10_weeks_matches:
        qs = qs.filter(created_at__gte=days_ago(DESIRED_MATCH_DURATION_WEEKS * 7))
        
    return qs


def match_free_play(
    qs=Match.objects.all(),
    **kwargs
):
    
    ## Like match ongoing but for matches older than 10 weeks
    return match_ongoing(
        qs, 
        last_interaction_days=LAST_INTERACTION_DAYS,
        only_consider_last_10_weeks_matches=False, 
        **kwargs).filter(created_at__lt=days_ago(DESIRED_MATCH_DURATION_WEEKS * 7))


def completed_match(
    qs=Match.objects.all(),
    min_total_mutual_messages=2,
    min_total_mutual_video_calls=0,
    last_interaction_days=LAST_INTERACTION_DAYS,
    last_and_first_interaction_days=5*7
):
    """
    8. Completed Match
    Filters matches that are over 10 weeks old, inactive, still in contact, and exchanged desired_x_messages and desired_x_video_calls.
    """
    qs = (
        qs.filter(
            support_matching=False,
            confirmed=True,
        )
        .filter(created_at__lt=days_ago(DESIRED_MATCH_DURATION_WEEKS * 7))
        .annotate(
            # TODO: also exlude messages send withing last interaction days here
            u1_messages=Count("user1__message_sender", filter=Q(user1__message_sender__recipient=F("user2"))),
            u2_messages=Count("user2__message_sender", filter=Q(user2__message_sender__recipient=F("user1"))),
            recent_messages_u1=Count("user1__message_sender", filter=Q(user1__message_sender__recipient=F("user2"), user1__message_sender__created__gte=days_ago(last_interaction_days))),
            recent_messages_u2=Count("user2__message_sender", filter=Q(user2__message_sender__recipient=F("user1"), user2__message_sender__created__gte=days_ago(last_interaction_days))),
            both_active_calls=Count("user1__u1_livekit_session", filter=Q(user1__u1_livekit_session__both_have_been_active=True)),
            recent_both_active_calls=Count("user1__u1_livekit_session", filter=Q(user1__u1_livekit_session__both_have_been_active=True, user1__u1_livekit_session__end_time__gte=days_ago(last_interaction_days))),
            last_message_time_u1=Max(
                "user1__message_sender__created",
                filter=Q(user1__message_sender__recipient=F("user2"))
            ),
            last_message_time_u2=Max(
                "user2__message_sender__created",
                filter=Q(user2__message_sender__recipient=F("user1"))
            ),
            last_call_time=Max(
                "user1__u1_livekit_session__end_time",
                filter=Q(user1__u1_livekit_session__both_have_been_active=True)
            ),
        )
        .annotate(
            mutual_messages=F("u1_messages") + F("u2_messages"),
            recent_mutual_messages=F("recent_messages_u1") + F("recent_messages_u2"),
            last_interaction=Greatest(
                "last_message_time_u1",
                "last_message_time_u2",
                "last_call_time"
            ),
        ).annotate(
            duration_since_last_interaction_in_days=ExtractDay(
                ExpressionWrapper(
                    F("last_interaction") - F("created_at"),
                    output_field=DurationField()
                )
            )
        )
        .filter(
            mutual_messages__gte=min_total_mutual_messages, 
            both_active_calls__gte=min_total_mutual_video_calls, 
            recent_mutual_messages=0, # No contact any more
            recent_both_active_calls=0, # no contact any more
            duration_since_last_interaction_in_days__gte=last_and_first_interaction_days
        )
    )
    return qs


def never_confirmed(qs=Match.objects.all()):
    """
    9. Never Confirmed
    Filters matches older than a specified number of days but still unconfirmed.
    """
    return qs.filter(confirmed=False, created_at__lt=days_ago(LAST_INTERACTION_DAYS))


def no_contact(qs=Match.objects.all()):  # TODO: re-name mutal ghosted?
    """
    10. No Contact
    Filters matches that are confirmed but no contact and older than a specified number of days.
    """
    return qs.filter(confirmed=True, created_at__lt=days_ago(LAST_INTERACTION_DAYS)).exclude(Q(user1__u1_livekit_session__is_active=True) | Q(user2__u2_livekit_session__is_active=True) | Q(user1__message_sender__created__gte=days_ago(LAST_INTERACTION_DAYS)) | Q(user2__message_sender__created__gte=days_ago(LAST_INTERACTION_DAYS)))


def user_ghosted(
        qs=Match.objects.all(),
        mutal_ghosted_days=DAYS_UNTILL_GHOSTED
    ):

    """
    11. User Ghosted
    Filters matches that are confirmed, have a single party contact, and are older than a specified number of days.
    """
    days_threshold = days_ago(mutal_ghosted_days)

    # Check if there is at least one message sent from user1 to user2
    user1_to_user2_message_exists = Message.objects.filter(
        sender=OuterRef('user1'),
        recipient=OuterRef('user2')
    )

    # Check if there is at least one message sent from user2 to user1
    user2_to_user1_message_exists = Message.objects.filter(
        sender=OuterRef('user2'),
        recipient=OuterRef('user1')
    )

    # Check if there's a video call either from user1 or user2
    video_call_exists = LivekitSession.objects.filter(
        Q(u1=OuterRef('user1'), u2=OuterRef('user2')) |
        Q(u1=OuterRef('user2'), u2=OuterRef('user1')),
       both_have_been_active=True, 
    )

    return qs.filter(
        support_matching=False,
        confirmed=True,
        created_at__lt=days_threshold,
    ).annotate(
        user1_to_user2_message_exists_flag=Exists(user1_to_user2_message_exists),
        user2_to_user1_message_exists_flag=Exists(user2_to_user1_message_exists),
        video_call_exists_flag=Exists(video_call_exists),
    ).filter(
        (
            Q(user1_to_user2_message_exists_flag=True, user2_to_user1_message_exists_flag=False) |
            Q(user1_to_user2_message_exists_flag=False, user2_to_user1_message_exists_flag=True)
        ) &
        Q(video_call_exists_flag=False)
    )


def contact_stopped(qs=Match.objects.all()):

    ## Basicly like a completed match, but the first and last interaction times are lass than 6 weeks appart
    qs = completed_match(qs, last_and_first_interaction_days=0).filter(
        duration_since_last_interaction_in_days__lte=5*7
    )
    return qs

def matching_proposals(qs=ProposedMatch.objects.all()):
    qs=ProposedMatch.objects.all().filter(
        closed=False,
        expires_at__gte=timezone.now(),
    )
    return qs

def expired_matching_proposals(qs=ProposedMatch.objects.all()):
    qs=ProposedMatch.objects.all().filter(
        closed=True,
        expires_at__lte=timezone.now(),
    )
    return qs
