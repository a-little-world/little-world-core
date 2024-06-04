from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count
from management.models.matches import Match

# Helper function to calculate days ago
def days_ago(days):
    return timezone.now() - timedelta(days=days)

# Per-Matching States Filters
DESIRED_MATCH_DURATION_WEEKS = 10

def match_unviewed(qs=Match.objects.all()):
    """
    1.L) TODO: Give appropriate name
    """
    return qs.filter(
        active=True,
        confirmed=False,
    ).distinct()
    
# TODO: Missing State for one user viewed match, utelizing 'confirmed_by' property

def match_confirmed_no_contact(qs=Match.objects.all()):
    """
    1) Match confirmed no contact
    TODO: not video calls (LivekitSession) and no messages (Message) from either of the match users
    """
    # Assuming XX days is 7 days for no contact
    return qs.filter(
        active=True,
        confirmed=True,
        report_unmatch__isnull=True,
        created_at__lt=days_ago(7),
    )

def match_confirmed_single_party_contact(qs=Match.objects.all()):
    """
    2) Match confirmed Single Party Contact
    TODO: Actually check the video calls (LivekitSession) and messages (Message) models if only one user contacted the other or not
    """
    return qs.filter(
        active=True,
        confirmed=True,
        report_unmatch__len=1, # TODO: Wrong this should allso check if there have been 
    )

def match_first_contact(qs=Match.objects.all()):
    """
    3) Match first contact
    TODO: they have hoth exchanged either a video call ( with both participated ) or send each other messages back and forth ( 1 messages with each of the users as sender at least )
    """
    return qs.filter(
        active=True,
        confirmed=True,
    )

def match_ongoing(qs=Match.objects.all()):
    """
    1) Match Ongoing
    TODO: they have exchanged multiples messages or video calls
    AND their last message or video call is less than 14 days ago
    AND their match isn't oder than DESIRED_MATCH_DURATION_WEEKS=10
    """
    return qs.filter(
        active=True,
        confirmed=True,
    )

def match_free_play(qs=Match.objects.all()):
    """
    2) Free Play
    TODO: match is over 10 weeks old and still active
    """
    return qs.filter(
        active=True,
        confirmed=True,
    )

def completed_match(
        qs=Match.objects.all(),
        desired_x_messages=2,
        desired_x_video_calls=2
    ):
    """
    1) Completed Match
    TODO OVER 10 weeks old and exchanged desired_x_messages desired_x_video_calls, from each match user to the other.
    Note exchanged always means for messags that both users have send X messags, and for video calls that there have X calls with the other user that both have participated in
    """
    return qs.filter(
        active=False,
        confirmed=True,
        still_in_contact_mail_send=True,
    )

def never_confirmed(qs=Match.objects.all()):
    """
    1) Never Confirmed
    TODO oder than XX days but still unconfirmed ( add a sensible global to top )
    """
    return qs.filter(
        active=True,
        confirmed=False,
    )

def no_contact(qs=Match.objects.all()):
    """
    2) No Contact
    TODO confirmed but no contact and older than XX days ( add a sensible global to top )
    """
    return qs.filter(
        active=True,
        confirmed=True,
    )

def user_ghosted(qs=Match.objects.all()):
    """
    3) User Ghosted
    TODO: basicly like 'Match confirmed Single Party Contact' but older than XX days ( add a sensible global to top )
    """
    return qs.filter(
        active=True,
        confirmed=True,
        report_unmatch__len=1,
        updated_at__lt=days_ago(14),
    )

def contact_stopped(qs=Match.objects.all(),
        stop_x_days_before_desired=21,
        desired_x_messages=2,
        desired_x_video_calls=2
                    ):
    """
    4) Contact stopped
    TODO: match older than DESIRED_MATCH_DURATION_WEEKS=10
    X message X video calls  exchanged but latest video calls or message exchaged was more than XX stop_x_days_before_desired days before the DESIRED_MATCH_DURATION_WEEKS
    Basicly meaning that the users interacted but their interaction stopped before the match was as longs as it should have been
    Note exchanged always means for messags that both users have send X messags, and for video calls that there have X calls with the other user that both have participated in
    """
    return qs.filter(
        active=True,
        confirmed=True,
        updated_at__lt=days_ago(30),
        created_at__gt=days_ago(84),
    )