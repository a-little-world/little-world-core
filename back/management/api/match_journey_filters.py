from django.db.models import Q, Count, F
from management.models.matches import Match
from video.models import LivekitSession
from chat.models import Message

# Helper function to calculate days ago
from datetime import timedelta
from django.utils import timezone
def days_ago(days):
    return timezone.now() - timedelta(days=days)

# Per-Matching States Filters
DESIRED_MATCH_DURATION_WEEKS = 10
NO_CONTACT_DAYS = 7
OLDER_THAN_DAYS = 14

def match_unviewed(qs=Match.objects.all()):
    """
    1. Match Unviewed
    Filters matches that are active and not yet confirmed by both users.
    """
    return qs.filter(
        support_matching=False, # generally remove support matches if they are 'unviewed' user has prob not finished sign-up
        active=True,
        confirmed=False,
    ).distinct()
    
def match_one_user_viewed(qs=Match.objects.all()):
    """
    2. Match One User Viewed
    Filters matches that are active, not yet confirmed by both users, but confirmed by at least one user.
    """
    return qs.filter(
        support_matching=False,
        active=True,
        confirmed=False,
        confirmed_by__isnull=False,
    ).distinct()

def match_confirmed_no_contact(qs=Match.objects.all()):
    """
    3. Match Confirmed No Contact
    Filters matches that are active, confirmed by both users, no unmatch reports, and neither user has sent messages or participated in video calls at all.
    """
    return qs.filter(
        support_matching=False,
        active=True,
        confirmed=True,
        report_unmatch__isnull=True,
        created_at__lt=days_ago(NO_CONTACT_DAYS),
    ).exclude(
        Q(user1__u1_livekit_session__is_active=True) | Q(user2__u2_livekit_session__is_active=True) |
        Q(user1__message_sender__isnull=False) | # No message should be sent between them at all
        Q(user2__message_sender__isnull=False)
    )

def match_confirmed_single_party_contact(qs=Match.objects.all()):
    """
    4. Match Confirmed Single Party Contact
    Filters matches that are active, confirmed, with one user having reported the unmatch or only one user having contacted the other.
    """
    return qs.filter(
        support_matching=False,
        active=True,
        confirmed=True,
    ).annotate(
        u1_messages=Count('user1__message_sender', filter=Q(user1__message_sender__recipient=F('user2'))),
        u2_messages=Count('user2__message_sender', filter=Q(user2__message_sender__recipient=F('user1')))
    ).filter(
        Q(report_unmatch__len=1) | Q(u1_messages=0) | Q(u2_messages=0)
    )

def match_first_contact(qs=Match.objects.all()):
    """
    5. Match First Contact
    Filters matches where both users have either participated in the same video call or sent at least one message to each other.
    """
    return qs.filter(
        Q(user1__u1_livekit_session__both_have_been_active=True) | Q(user2__u2_livekit_session__both_have_been_active=True),
        support_matching=False,
        active=True,
        confirmed=True,
    ).annotate(
        u1_messages=Count('user1__message_sender', filter=Q(user1__message_sender__recipient=F('user2'))),
        u2_messages=Count('user2__message_sender', filter=Q(user2__message_sender__recipient=F('user1')))
    ).annotate(
        mutual_messages=F('u1_messages') + F('u2_messages')
    ).filter(mutual_messages__gte=2)

def match_ongoing(
        qs=Match.objects.all(),
        last_interaction_days=14,
    ):
    """
    6. Match Ongoing
    Filters matches where users have exchanged multiple messages or video calls,
    their last message or video call is less than 14 days ago, and the match isn't older than DESIRED_MATCH_DURATION_WEEKS.
    """
    return qs.filter(
        active=True,
        support_matching=False,
        confirmed=True,
    ).annotate(
        u1_messages=Count('user1__message_sender', filter=Q(user1__message_sender__recipient=F('user2'))),
        u2_messages=Count('user2__message_sender', filter=Q(user2__message_sender__recipient=F('user1'))),
        recent_messages_u1=Count('user1__message_sender', 
            filter=Q(user1__message_sender__recipient=F('user2'), user1__message_sender__created__gte=days_ago(last_interaction_days))),
        recent_messages_u2=Count('user2__message_sender', 
            filter=Q(user2__message_sender__recipient=F('user1'), user2__message_sender__created__gte=days_ago(last_interaction_days))), 
        both_active_calls=Count('user1__u1_livekit_session', 
            filter=Q(user1__u1_livekit_session__both_have_been_active=True)),
        recent_both_active_calls=Count('user1__u1_livekit_session', 
            filter=Q(user1__u1_livekit_session__both_have_been_active=True, user1__u1_livekit_session__end_time__gte=days_ago(last_interaction_days)))
    ).annotate(
        mutual_messages=F('u1_messages') + F('u2_messages'),
        recent_mutual_messages=F('recent_messages_u1') + F('recent_messages_u2'),
    ).filter(
        # mutual_messages__gte=2,
        both_active_calls__gte=1,
        # recent_mutual_messages__gte=1,
    )

def match_free_play(qs=Match.objects.all()):
    """
    7. Free Play
    Filters matches that are over 10 weeks old and still active.
    Also ensure the match is still 'ongoing' like above.
    """
    return qs.filter(
        active=True,
        confirmed=True,
        created_at__lt=days_ago(DESIRED_MATCH_DURATION_WEEKS * 7)
    ).annotate(
        recent_messages=Count('message', filter=Q(message__created__gte=days_ago(NO_CONTACT_DAYS))),
        recent_video_calls=Count('livekitsession', filter=Q(livekitsession__end_time__gte=days_ago(NO_CONTACT_DAYS)))
    ).filter(
        Q(recent_messages__gte=1) | Q(recent_video_calls__gte=1)
    )

def completed_match(qs=Match.objects.all(), desired_x_messages=2, desired_x_video_calls=2):
    """
    8. Completed Match
    Filters matches that are over 10 weeks old, inactive, still in contact, and exchanged desired_x_messages and desired_x_video_calls.
    """
    return qs.filter(
        active=False,
        confirmed=True,
        still_in_contact_mail_send=True,
        created_at__lt=days_ago(DESIRED_MATCH_DURATION_WEEKS * 7)
    ).annotate(
        u1_messages=Count('user1__message_sender', filter=Q(message__sender=F('user1'))),
        u2_messages=Count('user2__message_sender', filter=Q(message__sender=F('user2'))),
        mutual_video_calls=Count('livekitsession', filter=Q(livekitsession__both_have_been_active=True))
    ).filter(
        Q(u1_messages__gte=desired_x_messages) & Q(u2_messages__gte=desired_x_messages) &
        Q(mutual_video_calls__gte=desired_x_video_calls)
    )

def never_confirmed(qs=Match.objects.all()):
    """
    9. Never Confirmed
    Filters matches older than a specified number of days but still unconfirmed.
    """
    return qs.filter(
        active=True,
        confirmed=False,
        created_at__lt=days_ago(OLDER_THAN_DAYS)
    )

def no_contact(qs=Match.objects.all()):
    """
    10. No Contact
    Filters matches that are confirmed but no contact and older than a specified number of days.
    """
    return qs.filter(
        active=True,
        confirmed=True,
        created_at__lt=days_ago(OLDER_THAN_DAYS)
    ).exclude(
        Q(user1__u1_livekit_session__is_active=True) | Q(user2__u2_livekit_session__is_active=True) |
        Q(user1__message_sender__created__gte=days_ago(OLDER_THAN_DAYS)) |
        Q(user2__message_sender__created__gte=days_ago(OLDER_THAN_DAYS))
    )

def user_ghosted(qs=Match.objects.all()):
    """
    11. User Ghosted
    Filters matches that are confirmed, have a single party contact, and are older than a specified number of days.
    """
    return qs.filter(
        active=True,
        confirmed=True,
        report_unmatch__len=1,
        updated_at__lt=days_ago(OLDER_THAN_DAYS),
    )

def contact_stopped(qs=Match.objects.all(), stop_x_days_before_desired=21, desired_x_messages=2, desired_x_video_calls=2):
    """
    12. Contact Stopped
    Filters matches older than DESIRED_MATCH_DURATION_WEEKS where users interacted but their interaction stopped before the desired duration.
    """
    return qs.filter(
        active=True,
        confirmed=True,
        created_at__gt=days_ago(DESIRED_MATCH_DURATION_WEEKS * 7),
    ).annotate(
        u1_messages=Count('user1__message_sender', filter=Q(message__sender=F('user1'))),
        u2_messages=Count('user2__message_sender', filter=Q(message__sender=F('user2'))),
        mutual_video_calls=Count('livekitsession', filter=Q(livekitsession__both_have_been_active=True))
    ).filter(
        Q(u1_messages__gte=desired_x_messages) & Q(u2_messages__gte=desired_x_messages) &
        Q(mutual_video_calls__gte=desired_x_video_calls) &
        (Q(user1__message_sender__created__lt=days_ago(stop_x_days_before_desired)) | 
         Q(user2__message_sender__created__lt=days_ago(stop_x_days_before_desired)) | 
         Q(livekitsession__end_time__lt=days_ago(stop_x_days_before_desired)))
    )