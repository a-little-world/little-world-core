from datetime import timedelta

from django.db.models import BigIntegerField, Case, Count, F, Max, Q, When
from django.utils import timezone

from management.api.match_journey_filters import (
    completed_match,
    contact_stopped,
    match_confirmed_no_contact,
    match_confirmed_single_party_contact,
    match_first_contact,
    match_free_play,
    match_one_user_viewed,
    match_ongoing,
    match_unviewed,
    matching_proposals,
    never_confirmed,
    no_contact,
    reported_or_removed_match,
    user_ghosted,
)
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.profile import Profile
from management.models.state import State
from management.models.unconfirmed_matches import ProposedMatch
from management.models.user import User


# Helper function to calculate three weeks ago
def three_weeks_ago():
    return timezone.now() - timedelta(weeks=3)


def days_ago(days):
    return timezone.now() - timedelta(days=days)


# Sign-Up Filters


def user_created(qs=User.objects.all()):
    """
    (Sign-Up) User was created, but still has to verify mail, fill form and have a prematching call
    """
    return qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__unresponsive=False,
        state__email_authenticated=False,
        # state__had_prematching_call=False,
    )


def email_verified(qs=User.objects.all()):
    """
    (Sign-Up) User has verified email, but still has to fill form and have a prematching call
    """
    return qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        # state__had_prematching_call=False, we marked some users as 'had_prematching_call' automatically, therefore we cannot require it to be False here!
    )


def user_form_completed(qs=User.objects.all()):
    """
    (Sign-Up) User has filled form, but still has to have a prematching call
    """
    return qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=False,
        prematchingappointment__isnull=True,
    ).exclude(
        profile__lang_skill__contains=[
            {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
        ],
    )
    
def never_active_or_deleted(qs=User.objects.all()):
    ud = user_deleted(qs)
    return qs.filter(
        Q(is_active=False) | Q(id__in=ud) | Q(
            state__user_form_state=State.UserFormStateChoices.UNFILLED,
            state__email_authenticated=False,
        )
    )

def never_active_or_deleted_or_created(qs=User.objects.all()):
    ud = user_deleted(qs)
    #na = never_active(qs)
    created = user_created(qs)
    return qs.filter(id__in=ud) | qs.filter(id__in=created)

def email_verified_and_form_completed(qs=User.objects.all()):
    ev = email_verified(qs)
    fc = user_form_completed(qs)
    # also not! too low german level
    return qs.filter(Q(id__in=ev) | Q(id__in=fc)).exclude(
        profile__lang_skill__contains=[
            {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
        ],
    )

def email_not_verified_or_form_not_completed(qs=User.objects.all()):
    ev = email_verified(qs)
    fc = user_form_completed(qs)
    never_active_or_delete_or_created = never_active_or_deleted_or_created(qs)
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=False,
    ).exclude(id__in=never_active_or_delete_or_created)

def too_low_german_level_or_not_onboarded(qs=User.objects.all()):
    tlg = too_low_german_level(qs)
    never_active_or_delete_or_created = never_active_or_deleted_or_created(qs)
    _email_not_verified_or_form_not_completed = email_verified_and_form_completed(qs)
    return qs.filter(
        Q(id__in=tlg) | Q(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=False,
        )
    ).exclude(id__in=never_active_or_delete_or_created).exclude(id__in=_email_not_verified_or_form_not_completed)

def not_too_low_german_level__is_onboarded(qs=User.objects.all()):
    tlg = too_low_german_level(qs)
    return qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    ).exclude(id__in=tlg)

def booked_onboarding_call(qs=User.objects.all()):
    """
    (Sign-Up) User has filled form and booked onboarding call
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
            num_appointments=Count(
                "prematchingappointment", filter=Q(prematchingappointment__end_time__gt=timezone.now())
            ),
        )
        .filter(num_appointments__gt=0)
        .exclude(id__in=no_shows)
    )


# Active User Filters


def first_search_v1(qs=User.objects.all()):
    """
    (Sign-Up) User is doing first search i.e.: has no 'non-support' match
    """

    now = timezone.now()
    users_with_open_proposals = ProposedMatch.objects.filter(
        closed=False, expires_at__gt=now, learner_when_created__isnull=False
    ).values_list("user1", "user2")

    users_w_open_proposals = set([id for pair in users_with_open_proposals for id in pair])
    users_w_open_proposals = qs.filter(id__in=users_w_open_proposals)

    searched_too_long = over_30_days_after_prematching_still_searching(qs)

    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__searching_state=State.SearchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        )
        .exclude(id__in=users_w_open_proposals)
        .exclude(id__in=searched_too_long)
        .annotate(
            num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False))
            + Count("match_user2", filter=Q(match_user2__support_matching=False))
        )
        .filter(num_matches=0)
    )


def first_search_v2(qs=User.objects.all(), require_min_lang_level=True):
    """
    (Sign-Up) User is doing first search i.e.: has no 'non-support' match
    """

    now = timezone.now()
    users_with_open_proposals = ProposedMatch.objects.filter(
        closed=False, expires_at__gt=now, learner_when_created__isnull=False
    ).values_list("user1", "user2")

    users_w_open_proposals = set([id for pair in users_with_open_proposals for id in pair])
    users_w_open_proposals = qs.filter(id__in=users_w_open_proposals)

    qs = qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__searching_state=State.SearchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        ).exclude(id__in=users_w_open_proposals).annotate(
            num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False))
            + Count("match_user2", filter=Q(match_user2__support_matching=False))
        ).filter(num_matches=0)
        
    if require_min_lang_level:
        qs = qs.exclude(
            profile__lang_skill__contains=[
                {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
            ],
        )
    return qs


def first_search_volunteers(qs=User.objects.all()):
    """
    (Sign-Up) VOLUNTEERS User is doing first search i.e.: has no 'non-support' match
    """
    fs = first_search_v1(qs)
    return fs.filter(profile__user_type=Profile.TypeChoices.VOLUNTEER, is_active=True)


def first_search_learners(qs=User.objects.all()):
    """
    (Sign-Up) LEARNERS User is doing first search i.e.: has no 'non-support' match
    """
    fs = first_search_v1(qs)
    return fs.filter(profile__user_type=Profile.TypeChoices.LEARNER, is_active=True)


def user_searching(qs=User.objects.all()):
    """
    (Active-User) User is searching and has at least one match
    """
    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__searching_state=State.SearchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        )
        .annotate(
            num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False))
            + Count("match_user2", filter=Q(match_user2__support_matching=False))
        )
        .filter(num_matches__gt=0)
    )
    
def user_searching_again(qs=User.objects.all()):
    return user_searching(qs).filter(num_matches__gt=1)

def pre_matching(qs=User.objects.all()):
    """
    (Active-User) User has an open proposed match
    """
    user_with_freeplay_matches = get_user_involved(match_free_play(), qs)
    user_with_completed_matches = get_user_involved(completed_match(), qs)

    users_with_proposals = get_user_involved(matching_proposals(), qs)

    qs = (
        qs.exclude(
            id__in=user_with_freeplay_matches,
        )
        .exclude(
            id__in=user_with_completed_matches,
        )
        .filter(id__in=users_with_proposals)
    )

    return qs


def match_takeoff(qs=User.objects.all()):
    """
    (Active-User) User has a confirmed match
    """

    user_with_freeplay_matches = get_user_involved(match_free_play(), qs)
    user_with_completed_matches = get_user_involved(completed_match(), qs)
    users_with_proposals = get_user_involved(matching_proposals(), qs)
    users_with_ongoing_matches = get_user_involved(match_ongoing(), qs)

    matches_unviewed = get_user_involved(match_unviewed(), qs)
    matches_one_user_viewed = get_user_involved(match_one_user_viewed(), qs)
    matches_confirmed_no_contact = get_user_involved(match_confirmed_no_contact(), qs)
    matches_confirmed_single_contact = get_user_involved(match_confirmed_single_party_contact(), qs)
    first_contact = get_user_involved(match_first_contact(), qs)

    qs = qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    )

    qs = (
        qs.exclude(
            id__in=user_with_freeplay_matches,
        )
        .exclude(
            id__in=user_with_completed_matches,
        )
        .exclude(id__in=users_with_proposals)
        .exclude(id__in=users_with_ongoing_matches)
        .filter(
            Q(id__in=matches_unviewed)
            | Q(id__in=matches_one_user_viewed)
            | Q(id__in=matches_confirmed_no_contact)
            | Q(id__in=matches_confirmed_single_contact)
            | Q(id__in=first_contact)
        )
    )

    return qs


def ongoing_non_completed_match(qs=User.objects.all()):
    """
    Ongoing Match that has not completed yet
    """
    qs = qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    )

    users_with_freeplay_matches = get_user_involved(match_free_play(), qs)
    users_with_completed_matches = get_user_involved(completed_match(), qs)

    users_with_ongoing_matches = get_user_involved(match_ongoing(), qs)

    qs = (
        qs.exclude(
            id__in=users_with_freeplay_matches,
        )
        .exclude(
            id__in=users_with_completed_matches,
        )
        .filter(id__in=users_with_ongoing_matches)
    )

    return qs


def active_match(qs=User.objects.all()):
    """
    (Active-User) User has and confirmed and ongoing match, that is still having video calls or sending messages
    """
    from management.api.match_journey_filters import match_ongoing

    filtered_matches = Match.objects.filter(Q(user1__in=qs) | Q(user2__in=qs))
    ongoing_matches = match_ongoing(
        qs=filtered_matches, last_interaction_days=21, only_consider_last_10_weeks_matches=False
    )

    users = User.objects.filter(
        Q(match_user1__in=ongoing_matches) | Q(match_user2__in=ongoing_matches),
        state__had_prematching_call=True,
        is_active=True,
    ).distinct()

    return users


def never_active(qs=User.objects.all(), days_since_creation=30):
    """
    (Inactive-User) Didn't ever become active
    """
    return qs.filter(
        date_joined__lt=days_ago(days_since_creation),
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=False,
        state__had_prematching_call=False,
        state__unresponsive=False,
        is_active=True,
    ).exclude(
        profile__lang_skill__contains=[
            {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
        ],
    )


def no_show(qs=User.objects.all()):
    """
    (Inactive-User) Didn't show up to onboarding call
    """
    return (
        qs.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=False,
            prematchingappointment__isnull=False,
            is_active=True,
        )
        .filter(prematchingappointment__end_time__lt=timezone.now())
        .exclude(
            profile__lang_skill__contains=[
                {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
            ],
        )
    )


def ghoster(qs=User.objects.all()):
    """
    (Inactive-User) User has matching in [3.G] 'ghosted' his match
    """
    # TODO: depricated!!!!
    # ghosted_matches = user_ghosted().annotate(
    #    ghosted_user=Case(
    #        When(user1_to_user2_message_exists_flag=False, then=F('user1')),
    #        When(user2_to_user1_message_exists_flag=False, then=F('user2')),
    #        output_field=BigIntegerField()
    #    )
    # )
    # ghosted_user_ids = ghosted_matches.values_list('ghosted_user', flat=True)
    return qs  # .filter(id__in=ghosted_user_ids, is_active=True)


def get_user_involved(match_qs, user_qs):
    users = match_qs.values_list("user1", "user2")
    users = [id for pair in users for id in pair]
    users = set(users)
    return user_qs.filter(id__in=users)


def failed_matching(qs=User.objects.all()):
    """
    (Inactive-User) User has a 'never_confirmed' or 'no_contact' or 'single_party_contact' or 'ghosted' or 'contact_stopped' or 'reported_or_unmatched' match
    """
    qs = qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    )

    user_with_freeplay_matches = get_user_involved(match_free_play(), qs)
    user_with_completed_matches = get_user_involved(completed_match(), qs)
    user_with_ongoing_matches = get_user_involved(match_ongoing(), qs)
    users_with_first_contact_matches = get_user_involved(match_first_contact(), qs)

    user_with_never_confirmed_matches = get_user_involved(never_confirmed(), qs)
    user_with_no_contact_matches = get_user_involved(no_contact(), qs)
    user_with_single_party_contact_matches = get_user_involved(match_confirmed_single_party_contact(), qs)
    user_with_ghosted_matches = get_user_involved(user_ghosted(), qs)
    user_with_contact_stopped_matches = get_user_involved(contact_stopped(), qs)
    user_with_reported_or_unmatched_matchings = get_user_involved(reported_or_removed_match(), qs)

    qs = (
        qs.exclude(id__in=user_with_freeplay_matches)
        .exclude(
            id__in=user_with_completed_matches,
        )
        .exclude(id__in=user_with_ongoing_matches)
        .exclude(id__in=users_with_first_contact_matches)
    )

    return qs.filter(
        Q(id__in=user_with_never_confirmed_matches)
        | Q(id__in=user_with_no_contact_matches)
        | Q(id__in=user_with_ghosted_matches)
        | Q(id__in=user_with_contact_stopped_matches)
        | Q(id__in=user_with_reported_or_unmatched_matchings)
        | Q(id__in=user_with_single_party_contact_matches)
    )


def no_confirm(qs=User.objects.all()):
    """
    (Inactive-User) Learner that has matching in 'Never Confirmed'
    """
    qs = qs.filter(
        is_active=True,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
    )

    user_with_freeplay_matches = get_user_involved(match_free_play(), qs)
    user_with_completed_matches = get_user_involved(completed_match(), qs)
    user_with_ongoing_matches = get_user_involved(match_ongoing(), qs)

    user_with_never_confirmed_matches = get_user_involved(never_confirmed(), qs)

    qs = (
        qs.exclude(id__in=user_with_freeplay_matches)
        .exclude(
            id__in=user_with_completed_matches,
        )
        .exclude(id__in=user_with_ongoing_matches)
    )

    return qs.filter(id__in=user_with_never_confirmed_matches)


def happy_inactive(qs=User.objects.all()):
    """
    (Inactive-User) Not searching, 1 or more matches at least one match in 'Completed Matching'
    """
    # Users that are not searching and have a 'completed_match' and NO 'free-play-match'
    users_with_freeplay_matches = get_user_involved(match_free_play(), qs)
    users_with_completed_matches = get_user_involved(completed_match(), qs)

    return qs.filter(Q(id__in=users_with_completed_matches) & ~Q(id__in=users_with_freeplay_matches))


def happy_active(qs=User.objects.all()):
    """
    (Inactive-User) Not searching, 1 or more matches at least one match in 'Completed Matching'
    """
    # Users that are not searching and have a 'completed_match' and NO 'free-play-match'
    users_with_freeplay_matches = get_user_involved(match_free_play(), qs)

    return qs.filter(id__in=users_with_freeplay_matches)


def too_low_german_level(qs=User.objects.all()):
    """
    (Inactive-User) User never active, but was flagged with a 'state.to_low_german_level=True'
    """
    return qs.filter(
        is_active=True,
        state__had_prematching_call=False,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        profile__lang_skill__contains=[
            {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
        ],
        profile__user_type=Profile.TypeChoices.LEARNER,
    )


# used to be 'unmatched'
def over_30_days_after_prematching_still_searching(qs=User.objects.all()):
    """
    (Inactive-User) 'first-search' for over XX days, we failed to match the user at all
    """
    # Assuming XX days is 30 days
    # Also filter out users that have open proposals
    thirty_days_ago = timezone.now() - timedelta(days=30)
    return (
        qs.annotate(latest_appointment=Max("prematchingappointment__end_time"))
        .filter(
            latest_appointment__lt=thirty_days_ago,
            is_active=True,
            prematchingappointment__end_time__lt=thirty_days_ago,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__searching_state=State.SearchingStateChoices.SEARCHING,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
            date_joined__lt=thirty_days_ago,
        )
        .annotate(
            num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False))
            + Count("match_user2", filter=Q(match_user2__support_matching=False))
        )
        .filter(num_matches=0)
    )


def gave_up_searching(qs=User.objects.all()):
    """
    (Inactive-User) User that's `searching=False` and has 0 matches
    """
    user_with_reported_or_unmatched_matchings = get_user_involved(reported_or_removed_match(), qs)
    user_with_never_confirmed_matches = get_user_involved(never_confirmed(), qs)
    user_with_no_contact_matches = get_user_involved(match_confirmed_no_contact(), qs)
    user_with_ghosted_matches = get_user_involved(user_ghosted(), qs)
    user_with_contact_stopped_matches = get_user_involved(contact_stopped(), qs)

    return (
        qs.filter(
            is_active=True,
            state__searching_state=State.SearchingStateChoices.IDLE,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,
        )
        .exclude(
            Q(id__in=user_with_never_confirmed_matches)
            | Q(id__in=user_with_no_contact_matches)
            | Q(id__in=user_with_ghosted_matches)
            | Q(id__in=user_with_contact_stopped_matches)
            | Q(id__in=user_with_reported_or_unmatched_matchings)
        )
        .annotate(
            num_matches=Count("match_user1", filter=Q(match_user1__support_matching=False))
            + Count("match_user2", filter=Q(match_user2__support_matching=False))
        )
        .filter(num_matches=0)
    )


def marked_unresponsive(qs=User.objects.all()):
    """
    All users in 'searching' without any user that has an open proposal!
    """
    return qs.filter(
        is_active=True,
        state__unresponsive=True,
    )


def user_deleted(qs=User.objects.all()):
    """
    (Past-User) User has been deleted
    """
    # we exclude all users that had a good match but deleted their account later ( they should be discounted! )
    _happy_inactive = happy_inactive(qs)
    return qs.filter(is_active=False).exclude(id__in=_happy_inactive)


def subscribed_to_newsletter(qs=User.objects.all()):
    """
    Subscribed to newsletter filter
    """
    return qs.filter(profile__newsletter_subscribed=True).order_by("-date_joined")


def community_calls(qs=User.objects.all(), last_x_days=28 * 3):
    """
    Community Calls filter
    """
    selected_fields = ["id"]  # Adjust these fields as needed for your User model

    users_in_signup = (
        user_created(qs)
        .values(*selected_fields)
        .union(
            user_form_completed(qs).values(*selected_fields),
            email_verified(qs).values(*selected_fields),
            booked_onboarding_call(qs).values(*selected_fields),
            first_search_v2(qs).values(*selected_fields),
        )
    )
    users_in_signup = User.objects.filter(id__in=users_in_signup).distinct()

    users_in_signup = users_in_signup.filter(date_joined__gte=days_ago(last_x_days))

    prematching_users = (
        pre_matching(qs)
        .values(*selected_fields)
        .union(
            match_takeoff(qs).values(*selected_fields),
            active_match(qs).values(*selected_fields),
        )
    )

    prematching_users = User.objects.filter(id__in=prematching_users).distinct()

    all_users = users_in_signup.values(*selected_fields).union(prematching_users.values(*selected_fields))
    all_distinct_users = User.objects.filter(id__in=all_users).distinct()

    return all_distinct_users

def completed_form__created_within_6months(qs=User.objects.all()):
    """
    Completed form within 6 months
    """
    return qs.filter(date_joined__gte=days_ago(6 * 30))

def completed_form__no__onboarding_call(qs=User.objects.all()):
    """
    Completed form but no onboarding call
    """
    return qs.filter(state__user_form_state=State.UserFormStateChoices.FILLED, state__had_prematching_call=False)

def completed_form__created_within_6months_no_onboarding_call(qs=User.objects.all()):
    """
    Completed form within 6 months but no onboarding call
    """
    return qs.filter(date_joined__gte=days_ago(6 * 30), state__had_prematching_call=False)

def completed_form__created_within_6months_no_onboarding_call_volunteer(qs=User.objects.all()):
    """
    Completed form within 6 months but no onboarding call
    """
    return qs.filter(date_joined__gte=days_ago(6 * 30), state__had_prematching_call=False, profile__user_type=Profile.TypeChoices.VOLUNTEER)