from dataclasses import dataclass
from typing import List
from management.models.dynamic_user_list import DynamicUserList
from management.api.user_advanced_filter import (
    all_users,
    needs_matching,
    needs_matching_volunteers,
    searching_users,
    users_in_registration,
    active_within_3weeks,
    get_active_match_query_set,
    get_quality_match_query_set,
    get_user_with_message_to_admin,
    get_user_with_message_to_admin_that_are_read_but_not_replied,
    users_with_open_proposals,
    users_with_open_tasks,
    users_with_booked_prematching_call,
    users_require_prematching_call_not_booked,
    get_volunteers_booked_onboarding_call_but_never_visited,
    only_hd_test_user,
)
from management.api.user_journey_filters import (
    failed_matching,
    user_created,
    email_verified,
    user_form_completed,
    booked_onboarding_call,
    first_search_v1,
    first_search_v2,
    first_search_learners,
    first_search_volunteers,
    user_searching,
    pre_matching,
    match_takeoff,
    active_match,
    never_active,
    user_deleted,
    no_show,
    ghoster,
    no_confirm,
    happy_inactive,
    happy_active,
    too_low_german_level,
    over_30_days_after_prematching_still_searching,
    gave_up_searching,
    community_calls,
    ongoing_non_completed_match,
    subscribed_to_newsletter,
    marked_unresponsive,
)


@dataclass
class FilterListEntry:
    name: str
    description: str
    queryset: callable = None

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
        }


PANEL_V1_FILTER_LISTS = [
    FilterListEntry("all", "All users ordered by date joined!", all_users),
    FilterListEntry(
        "searching",
        "Users who are searching for a match! Exclude users that have not finished the user form or verified their email!",
        searching_users,
    ),
    FilterListEntry(
        "needs_matching",
        "All users in 'searching' without any user that has an open proposal!",
        needs_matching,
    ),
    FilterListEntry(
        "in_registration",
        "Users who have not finished the user form or verified their email!",
        users_in_registration,
    ),
    FilterListEntry(
        "active_within_3weeks",
        "Users who have been active within the last 3 weeks!",
        active_within_3weeks,
    ),
    FilterListEntry(
        "active_match",
        "Users who have communicated with their match in the last 4 weeks",
        get_active_match_query_set,
    ),
    FilterListEntry(
        "highquality_matching",
        "Users who have at least one matching with 20+ Messages",
        get_quality_match_query_set,
    ),
    FilterListEntry(
        "message_reply_required",
        "Users who have an unread message to the admin user",
        get_user_with_message_to_admin,
    ),
    FilterListEntry(
        "read_message_but_not_replied",
        "Read messages to the management user that have not been replied to",
        get_user_with_message_to_admin_that_are_read_but_not_replied,
    ),
    FilterListEntry("users_with_open_tasks", "Users who have open tasks", users_with_open_tasks),
    FilterListEntry(
        "users_with_open_proposals",
        "Users who have open proposals",
        users_with_open_proposals,
    ),
    FilterListEntry(
        "volunteers_booked_onboarding_call_but_never_visited",
        "Volunteers who have booked an onboarding call but never visited",
        get_volunteers_booked_onboarding_call_but_never_visited,
    ),
    FilterListEntry(
        "users_require_prematching_call_not_booked",
        "Users that still require a pre-matching call before matching, but haven't booked one yet",
        users_require_prematching_call_not_booked,
    ),
    FilterListEntry(
        "users_with_booked_prematching_call",
        "Users that have booked a pre-matching call",
        users_with_booked_prematching_call,
    ),
    FilterListEntry(
        "users_with_booked_prematching_call_exclude_had",
        "Users that have booked a pre-matching call but have not had one yet",
        users_with_booked_prematching_call,
    ),
]

CORE_LISTS = [
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

USER_JOURNEY_FILTER_LISTS = [
    FilterListEntry(
        "journey_v2__user_created",
        "(Sign-Up) User was created, but still has to verify mail, fill form and have a prematching call",
        user_created,
    ),
    FilterListEntry(
        "journey_v2__email_verified",
        "(Sign-Up) User has verified email, but still has to fill form and have a prematching call",
        email_verified,
    ),
    FilterListEntry(
        "journey_v2__user_form_completed",
        "(Sign-Up) User has filled form, but still has to have a prematching call",
        user_form_completed,
    ),
    FilterListEntry(
        "journey_v2__booked_onboarding_call",
        "(Sign-Up) User has filled form and booked onboarding call",
        booked_onboarding_call,
    ),
    FilterListEntry(
        "journey_v2__first_search",
        "(Sign-Up) User is doing first search i.e.: has no 'non-support' match",
        first_search_v1,
    ),
    FilterListEntry(
        "journey_v2__first_search_v2",
        "(Sign-Up) User is doing first search i.e.: has no 'non-support' match",
        first_search_v2,
    ),
    FilterListEntry(
        "journey_v2__first_search_volunteers",
        "(Sign-Up) VOLUTEERS User is doing first search i.e.: has no 'non-support' match",
        first_search_learners,
    ),
    FilterListEntry(
        "journey_v2__first_search_learners",
        "(Sign-Up) learners User is doing first search i.e.: has no 'non-support' match",
        first_search_volunteers,
    ),
    FilterListEntry(
        "journey_v2__user_searching_again",
        "(Active-User) User is searching and has at least one match",
        user_searching,
    ),
    FilterListEntry(
        "journey_v2__pre_matching",
        "(Active-User) User has an open proposed match.",
        pre_matching,
    ),
    FilterListEntry(
        "journey_v2__match_takeoff",
        "(Active-User) User has a confirmed match.",
        match_takeoff,
    ),
    FilterListEntry(
        "journey_v2__active_matching",
        "(Active-User) User has and confirst and ongoing match, that is still having video calls or sending messages",
        active_match,
    ),
    FilterListEntry(
        "journey_v2__ongoing_non_completed_match",
        "Ongoing Match that has not completed yet",
        ongoing_non_completed_match,
    ),
    FilterListEntry(
        "journey_v2__never_active",
        "(Inactive-User) Didn't ever become active",
        never_active,
    ),
    FilterListEntry(
        "journey_v2__no_show",
        "(Inactive-User) Didn't show up to onboarding call",
        no_show,
    ),
    FilterListEntry(
        "journey_v2__user_ghosted",
        "(Inactive-User) User has matching in [3.G] 'ghosted' his match",
        ghoster,
    ),
    FilterListEntry(
        "journey_v2__no_confirm",
        "(Inactive-User) Learner that has matching in 'Never Confirmed'",
        no_confirm,
    ),
    FilterListEntry("journey_v2__failed_matching", "TODO", failed_matching),
    FilterListEntry(
        "journey_v2__happy_inactive",
        "(Inactive-User) Not searching, 1 or more matches at least one match in 'Completed Matching'",
        happy_inactive,
    ),
    FilterListEntry(
        "journey_v2__happy_active",
        "(Inactive-User) Not searching, 1 or more matches at least one match in 'Completed Matching'",
        happy_active,
    ),
    FilterListEntry(
        "journey_v2__too_low_german_level",
        "(Inactive-User) User never active, but was flagged with a 'state.to_low_german_level=True'",
        too_low_german_level,
    ),
    FilterListEntry(
        "journey_v2__unmatched",
        "(Inactive-User) 'first-search' for over XX days, we failed to match the user at all",
        over_30_days_after_prematching_still_searching,
    ),
    FilterListEntry(
        "journey_v2__gave_up_searching",
        "(Inactive-User) User that's `searching=False` and has 0 matches",
        gave_up_searching,
    ),
    FilterListEntry("journey_v2__user_deleted", "(Past-User) User has been deleted", user_deleted),
    FilterListEntry(
        "journey_v2__marked_unresponsive",
        "All users in 'searching' without any user that has an open proposal!",
        marked_unresponsive,
    ),
    FilterListEntry(
        "needs_matching_volunteers",
        "Volunteers only: All users in 'searching' without any user that has an open proposal!",
        needs_matching_volunteers,
    ),
    FilterListEntry("herrduenschnlate", "just a list of some test users for tim", only_hd_test_user),
    FilterListEntry("community", "Community Calls filter", community_calls),
    FilterListEntry(
        "newsletter_subscribed",
        "Subscribed to newsletter filter",
        subscribed_to_newsletter,
    ),
]

FILTER_LISTS = PANEL_V1_FILTER_LISTS + USER_JOURNEY_FILTER_LISTS


def get_dynamic_userlists() -> List[FilterListEntry]:
    return [FilterListEntry(":dyn:" + str(dyn_user_list.id), dyn_user_list.name) for dyn_user_list in DynamicUserList.objects.all()]


def get_choices():
    try:
        return [(entry.name, entry.description) for entry in FILTER_LISTS + get_dynamic_userlists()]
    except Exception as e:
        print(e)
        return []


def get_list_by_name(name):
    for element in FILTER_LISTS + get_dynamic_userlists():
        if element.name == name:
            return element
    return None
