from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count
from management.models.user import User
from management.models.state import State
from management.models.profile import Profile
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment

# Helper function to calculate three weeks ago
def three_weeks_ago():
    return timezone.now() - timedelta(weeks=3)

# Sign-Up Filters

def user_created(qs=User.objects.all()):
    """
    1.1: User was created, but still has to verify mail, fill form and have a prematching call
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__unresponsive=False,
        state__email_authenticated=False,
        state__had_prematching_call=False,
    )

def email_verified(qs=User.objects.all()):
    """
    1.2: User has verified email, but still has to fill form and have a prematching call
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=False,
    )

def user_form_completed(qs=User.objects.all()):
    """
    1.3: User has filled form, but still has to have a prematching call
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=False,
    ).annotate(
        num_appointments=Count(
            'prematchingappointment', 
            filter=Q(prematchingappointment__end_time__gt=timezone.now())),
    ).filter(
        num_appointments=0
    )

def booked_onboarding_call(qs=User.objects.all()):
    """
    1.4: User has filled form and booked onboarding call
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=False, # TODO: check if this is correct
    ).annotate(
        num_appointments=Count(
            'prematchingappointment', 
            filter=Q(prematchingappointment__end_time__gt=timezone.now())),
    ).filter(
        num_appointments__gt=0
    )

# Active User Filters

def first_search(qs=User.objects.all()):
    """
    2.1: User is doing first search i.e.: has no 'non-support' match
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__matching_state=State.MatchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    ).annotate( 
        num_matches=Count(
            'match_user1', 
            filter=Q(match_user1__support_matching=False)
        ) + Count(
            'match_user2', 
            filter=Q(match_user2__support_matching=False)
        )
    ).filter(
        num_matches=0
    )
    
def first_search_volunteers(qs=User.objects.all()):
    fs = first_search(qs)
    return fs.filter(
        profile__user_type=Profile.TypeChoices.VOLUNTEER
    )
    
def first_search_learners(qs=User.objects.all()):
    fs = first_search(qs)
    return fs.filter(
        profile__user_type=Profile.TypeChoices.LEARNER
    )

def user_searching(qs=User.objects.all()):
    """
    2.2: User is searching and has at least one match
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__matching_state=State.MatchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    ).annotate( 
        num_matches=Count(
            'match_user1', 
            filter=Q(match_user1__support_matching=False)
        ) + Count(
            'match_user2', 
            filter=Q(match_user2__support_matching=False)
        )
    ).filter(
        num_matches__gt=0
    )

def pre_matching(qs=User.objects.all()):
    """
    2.3: User has `Pre-Matching` or `Kickoff-Matching` Match.
    """
    return qs.filter(
        Q(unconfirmed_match_user1__closed=False) |
        Q(unconfirmed_match_user2__closed=False),
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__matching_state=State.MatchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    ).distinct()

def match_takeoff(qs=User.objects.all()):
    """
    2.4: User has `Pre-Matching` or `Kickoff-Matching` Match.
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__matching_state=State.MatchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    ).annotate( 
        num_matches=Count(
            'match_user1', 
            filter=Q(match_user1__support_matching=False)
        ) + Count(
            'match_user2', 
            filter=Q(match_user2__support_matching=False)
        )
    ).filter(
        num_matches__gt=0
    )
    
def active_match(qs=User.objects.all()):
    """
    2.5: User has and confirst and ongoing match, that is still having video calls or sending messages
    """
    from management.api.match_journey_filters import match_ongoing
    filtered_matches = Match.objects.filter(
        Q(user1__in=qs) | Q(user2__in=qs)
    )
    ongoing_matches = match_ongoing(
        qs=filtered_matches, 
        last_interaction_days=21
    )
    
    users = User.objects.filter(
        Q(match_user1__in=ongoing_matches) | Q(match_user2__in=ongoing_matches)
    )
    
    return users

# Inactive-User Filters

def never_active(qs=User.objects.all()):
    """
    0) 'Never-Active': Didn't ever become active
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=False,
        state__had_prematching_call=False,
        state__unresponsive=False
    )

def no_show(qs=User.objects.all()):
    """
    0.2) 'No Show': Didn't show up to onboarding call
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=False,
        prematchingappointment__isnull=False
    )

def ghoster(qs=User.objects.all()):
    """
    1) 'Ghoster': User has matching in [3.G] 'ghosted' his match
    return qs.filter(
        Q(match_user1__status=Match.StatusChoices.GHOSTED) |
        Q(match_user2__status=Match.StatusChoices.GHOSTED)
    ).distinct()
    TODO: broken
    """
    return qs

def no_confirm(qs=User.objects.all()):
    """
    2.L) 'No-Confirm': Learner that has matching in 'Never Confirmed'
    return qs.filter(
        Q(match_user1__status=Match.StatusChoices.NEVER_CONFIRMED) |
        Q(match_user2__status=Match.StatusChoices.NEVER_CONFIRMED)
    ).distinct()
    TODO: fix
    """
    return qs

def happy_inactive(qs=User.objects.all()):
    """
    3) 'Happy-Inactive': Not searching, 1 or more matches at least one match in 'Completed Matching'
    return qs.filter(
        state__matching_state=State.MatchingStateChoices.NOT_SEARCHING,
        Q(match_user1__status=Match.StatusChoices.COMPLETED) |
        Q(match_user2__status=Match.StatusChoices.COMPLETED)
    ).distinct()
    TODO - FIX
    """
    return qs

def too_low_german_level(qs=User.objects.all()):
    """
    4) 'Too Low german level': User never active, but was flagged with a 'state.to_low_german_level=True'
    need to check if the profile.lang_skill json list field contains {'lang': 'german', 'level': 'A1'}
    """
    return qs.filter(
        profile__lang_skill__contains=[{'lang': Profile.LanguageChoices.GERMAN, 'level': Profile.LanguageSkillChoices.LEVEL_0}]
    )

def unmatched(qs=User.objects.all()):
    """
    5) 'Unmatched': 'first-search' for over XX days, we failed to match the user at all
    """
    # Assuming XX days is 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__matching_state=State.MatchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
        date_joined__lt=thirty_days_ago
    ).annotate( 
        num_matches=Count(
            'match_user1', 
            filter=Q(match_user1__support_matching=False)
        ) + Count(
            'match_user2', 
            filter=Q(match_user2__support_matching=False)
        )
    ).filter(
        num_matches=0
    )

def gave_up_searching(qs=User.objects.all()):
    """
    6) 'Gave-Up-Searching': User that's `searching=False` and has 0 matches
    """
    return qs.filter(
        state__matching_state=State.MatchingStateChoices.IDLE,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    ).annotate( 
        num_matches=Count(
            'match_user1', 
            filter=Q(match_user1__support_matching=False)
        ) + Count(
            'match_user2', 
            filter=Q(match_user2__support_matching=False)
        )
    ).filter(
        num_matches=0
    )