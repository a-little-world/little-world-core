from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count, Case, F, BigIntegerField, When
from management.models.user import User
from management.models.state import State
from management.models.profile import Profile
from management.models.matches import Match
from management.models.unconfirmed_matches import ProposedMatch
from management.api.match_journey_filters import user_ghosted, never_confirmed, completed_match, match_free_play


# Helper function to calculate three weeks ago
def three_weeks_ago():
    return timezone.now() - timedelta(weeks=3)

def days_ago(days):
    return timezone.now() - timedelta(days=days)


# Sign-Up Filters


def user_created(qs=User.objects.all()):
    """
    1.1: User was created, but still has to verify mail, fill form and have a prematching call
    """
    return qs.filter(
        is_active=True,
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
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=False,
    )


def user_form_completed(qs=User.objects.all()):
    """
    1.3: User has filled form, but still has to have a prematching call
    """
    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=False,
            prematchingappointment__isnull=True,
        )
    )


def booked_onboarding_call(qs=User.objects.all()):
    """
    1.4: User has filled form and booked onboarding call
    """
    no_shows = no_show(qs)
    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=False,  # TODO: check if this is correct
        )
        .annotate(
            num_appointments=Count("prematchingappointment", filter=Q(prematchingappointment__end_time__gt=timezone.now())),
        )
        .filter(num_appointments__gt=0).exclude(id__in=no_shows)
    )


# Active User Filters


def first_search(qs=User.objects.all()):
    """
    2.1: User is doing first search i.e.: has no 'non-support' match
    """
    
    now = timezone.now()
    users_with_open_proposals = ProposedMatch.objects.filter(
        closed=False,
        expires_at__gt=now, 
        learner_when_created__isnull=False
    ).values_list('user1', 'user2')

    users_w_open_proposals = set([id for pair in users_with_open_proposals for id in pair])
    users_w_open_proposals = qs.filter(id__in=users_w_open_proposals)

    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__matching_state=State.MatchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True
        ).exclude(id__in=users_w_open_proposals)
        .annotate(num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False)) + Count("match_user2", filter=Q(match_user2__support_matching=False)))
        .filter(num_matches=0)
    )


def first_search_volunteers(qs=User.objects.all()):
    fs = first_search(qs)
    return fs.filter(profile__user_type=Profile.TypeChoices.VOLUNTEER, is_active=True)


def first_search_learners(qs=User.objects.all()):
    fs = first_search(qs)
    return fs.filter(profile__user_type=Profile.TypeChoices.LEARNER, is_active=True)


def user_searching(qs=User.objects.all()):
    """
    2.2: User is searching and has at least one match
    """
    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__matching_state=State.MatchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        )
        .annotate(num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False)) + Count("match_user2", filter=Q(match_user2__support_matching=False)))
        .filter(num_matches__gt=0)
    )


def pre_matching(qs=User.objects.all()):
    """
    2.3: User has `Pre-Matching` or `Kickoff-Matching` Match.
    """
    return qs.filter(
        Q(unconfirmed_match_user1__closed=False) | Q(unconfirmed_match_user2__closed=False),
        is_active=True,
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
    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__matching_state=State.MatchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        )
        .annotate(num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False)) + Count("match_user2", filter=Q(match_user2__support_matching=False)))
        .filter(num_matches__gt=0)
    )


def active_match(qs=User.objects.all()):
    """
    2.5: User has and confirst and ongoing match, that is still having video calls or sending messages
    """
    from management.api.match_journey_filters import match_ongoing

    filtered_matches = Match.objects.filter(Q(user1__in=qs) | Q(user2__in=qs))
    ongoing_matches = match_ongoing(qs=filtered_matches, last_interaction_days=21, only_consider_last_10_weeks_matches=False)

    users = User.objects.filter(Q(match_user1__in=ongoing_matches) | Q(match_user2__in=ongoing_matches), is_active=True).distinct()

    return users

def never_active(
        qs=User.objects.all()
    ):
    """
    0) 'Never-Active': Didn't ever become active
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.UNFILLED, 
        state__email_authenticated=False, 
        state__had_prematching_call=False, 
        state__unresponsive=False, 
        is_active=True
    )


def no_show(qs=User.objects.all()):
    """
    0.2) 
    'No Show': Didn't show up to onboarding call, so hads a prematchingappointment, that is in the past.
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED, 
        state__email_authenticated=True, 
        state__unresponsive=False, 
        state__had_prematching_call=False, 
        prematchingappointment__isnull=False, 
        is_active=True
    ).filter(
        prematchingappointment__end_time__lt=timezone.now()
    )


def ghoster(qs=User.objects.all()):
    ghosted_matches = user_ghosted().annotate(
        ghosted_user=Case(
            When(user1_to_user2_message_exists_flag=False, then=F('user1')),
            When(user2_to_user1_message_exists_flag=False, then=F('user2')),
            output_field=BigIntegerField()
        )
    )
    ghosted_user_ids = ghosted_matches.values_list('ghosted_user', flat=True)
    return qs.filter(id__in=ghosted_user_ids, is_active=True)


def no_confirm(qs=User.objects.all()):
    users_in_unconfirmed_matches = qs.filter(
        Q(match_user1__confirmed=False, match_user1__support_matching=False) | Q(match_user2__confirmed=False, match_user2__support_matching=False)
    ).distinct()
    users_in_confirmed_matches = qs.filter(
        Q(match_user1__confirmed=True, match_user1__support_matching=False) | Q(match_user2__confirmed=True, match_user2__support_matching=False)
    ).distinct()
    users_with_only_unconfirmed_matches = users_in_unconfirmed_matches.exclude(
        id__in=users_in_confirmed_matches.values('id')
    ).filter(profile__user_type=Profile.TypeChoices.LEARNER)
    return users_with_only_unconfirmed_matches


def happy_inactive(qs=User.objects.all()):
    # Users that are not searching and have a 'completed_match' and NO 'free-play-match'
    not_searching = qs.filter(state__matching_state=State.MatchingStateChoices.IDLE)

    users_that_have_free_play_matches = match_free_play().values_list('user1', 'user2')
    users_that_have_free_play_matches = [id for pair in users_that_have_free_play_matches for id in pair]
    users_that_have_free_play_matches = set(users_that_have_free_play_matches)
    users_that_have_free_play_matches = not_searching.filter(id__in=users_that_have_free_play_matches)
    users_that_have_free_play_matches = qs.filter(id__in=users_that_have_free_play_matches).filter(id__in=not_searching)
    
    users_that_have_finished_matches = completed_match().values_list('user1', 'user2')
    users_that_have_finished_matches = [id for pair in users_that_have_finished_matches for id in pair]
    users_that_have_finished_matches = set(users_that_have_finished_matches)
    users_that_have_finished_matches = not_searching.filter(id__in=users_that_have_finished_matches)
    users_that_have_finished_matches = qs.filter(id__in=users_that_have_finished_matches).filter(id__in=not_searching)
    
    happy_inactive_users = users_that_have_finished_matches.exclude(id__in=users_that_have_free_play_matches, is_active=False)

    return happy_inactive_users


def too_low_german_level(qs=User.objects.all()):
    """
    4) 'Too Low german level': User never active, but was flagged with a 'state.to_low_german_level=True'
    need to check if the profile.lang_skill json list field contains {'lang': 'german', 'level': 'A1'}
    """
    return qs.filter(
        is_active=True,
        profile__lang_skill__contains=[{"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}], 
        profile__user_type=Profile.TypeChoices.LEARNER)


def unmatched(qs=User.objects.all()):
    """
    5) 'Unmatched': 'first-search' for over XX days, we failed to match the user at all
    """
    # Assuming XX days is 30 days
    # Also filter out users that have open proposals
    thirty_days_ago = timezone.now() - timedelta(days=30)
    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED, 
            state__matching_state=State.MatchingStateChoices.SEARCHING, 
            state__email_authenticated=True, 
            state__unresponsive=False, 
            state__had_prematching_call=True, 
            date_joined__lt=thirty_days_ago)
        .annotate(num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False)) + Count("match_user2", filter=Q(match_user2__support_matching=False)))
        .filter(num_matches=0)
    )


def gave_up_searching(qs=User.objects.all()):
    """
    6) 'Gave-Up-Searching': User that's `searching=False` and has 0 matches
    """
    return (
        qs.filter(
            is_active=True,
            state__matching_state=State.MatchingStateChoices.IDLE,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        )
        .annotate(num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False)) + Count("match_user2", filter=Q(match_user2__support_matching=False)))
        .filter(num_matches=0)
    )


def user_deleted(qs=User.objects.all()):
    """
    7) 'User-Deleted': User that has been deleted
    """
    return qs.filter(is_active=False)


def subscribed_to_newsletter(qs=User.objects.all()):
    return qs.filter(profile__newsletter_subscribed=True).order_by("-date_joined")


def community_calls(
        qs=User.objects.all(),
        last_x_days=28*3
    ):
    selected_fields = ['id']  # Adjust these fields as needed for your User model

    users_in_signup = user_created(qs).values(*selected_fields).union(
        user_form_completed(qs).values(*selected_fields),
        email_verified(qs).values(*selected_fields),
        booked_onboarding_call(qs).values(*selected_fields),
        first_search(qs).values(*selected_fields)
    )
    users_in_signup = User.objects.filter(id__in=users_in_signup).distinct()
    
    users_in_signup = users_in_signup.filter(
        date_joined__gte=days_ago(last_x_days)
    )

    prematching_users = pre_matching(qs).values(*selected_fields).union(
        match_takeoff(qs).values(*selected_fields),
        active_match(qs).values(*selected_fields),
        match_takeoff(qs).values(*selected_fields)
    )

    prematching_users = User.objects.filter(id__in=prematching_users).distinct()

    all_users = users_in_signup.values(*selected_fields).union(
        prematching_users.values(*selected_fields)
    )
    all_distinct_users = User.objects.filter(id__in=all_users).distinct()
    
    return all_distinct_users