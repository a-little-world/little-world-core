from dataclasses import dataclass
from typing import List

from management.api.user_advanced_filter import (
    active_within_3weeks,
    all_users,
    get_active_match_query_set,
    get_quality_match_query_set,
    get_user_with_message_to_admin,
    get_user_with_message_to_admin_that_are_read_but_not_replied,
    get_volunteers_booked_onboarding_call_but_never_visited,
    get_users_with_company,
    needs_matching,
    needs_matching_volunteers,
    only_hd_test_user,
    searching_users,
    users_in_registration,
    users_require_prematching_call_not_booked,
    users_with_booked_prematching_call,
    users_with_open_proposals,
    users_with_open_tasks,
)
from management.api.user_journey_filters import (
    not_too_low_german_level__is_onboarded,
    email_not_verified_or_form_not_completed,
    too_low_german_level_or_not_onboarded,
    email_verified_and_form_completed,
    never_active_or_deleted_or_created,
    active_match,
    booked_onboarding_call,
    learners_with_a1a2,
    community_calls,
    learners_better_than_a1a2,
    community__ehrenamtliche_und_lernende_with_a1a2,
    community__learners_better_than_a1a2,
    email_verified,
    failed_matching,
    first_search_learners,
    first_search_v1,
    first_search_v2,
    first_search_volunteers,
    gave_up_searching,
    ghoster,
    happy_active,
    happy_inactive,
    marked_unresponsive,
    match_takeoff,
    never_active,
    no_confirm,
    no_show,
    ongoing_non_completed_match,
    over_30_days_after_prematching_still_searching,
    pre_matching,
    subscribed_to_newsletter,
    too_low_german_level,
    user_created,
    never_active_or_deleted,
    user_deleted,
    user_form_completed,
    user_searching,
    completed_form__no__onboarding_call,
    completed_form__created_within_6months,
    completed_form__created_within_6months_no_onboarding_call,
    completed_form__created_within_6months_no_onboarding_call_volunteer,
    all_volunteers_min_one_no_ongoing_match,
    volunteers_with_completed_match_no_ongoing,
)
from management.models.dynamic_user_list import DynamicUserList


@dataclass
class FilterListEntry:
    name: str
    description: str | None
    queryset: callable = None

    def to_dict(self):
        description = self.description
        if description is None and self.queryset and self.queryset.__doc__:
            description = self.queryset.__doc__.strip()
        return {
            "name": self.name,
            "description": description,
        }


PANEL_V1_FILTER_LISTS = [
    FilterListEntry("all", None, all_users),
    FilterListEntry("searching", None, searching_users),
    FilterListEntry("needs_matching", None, needs_matching),
    FilterListEntry("in_registration", None, users_in_registration),
    FilterListEntry("active_within_3weeks", None, active_within_3weeks),
    FilterListEntry("active_match", None, get_active_match_query_set),
    FilterListEntry("highquality_matching", None, get_quality_match_query_set),
    FilterListEntry("message_reply_required", None, get_user_with_message_to_admin),
    FilterListEntry("read_message_but_not_replied", None, get_user_with_message_to_admin_that_are_read_but_not_replied),
    FilterListEntry("users_with_company", None, get_users_with_company),
    FilterListEntry("users_with_open_tasks", None, users_with_open_tasks),
    FilterListEntry("users_with_open_proposals", None, users_with_open_proposals),
    FilterListEntry("volunteers_booked_onboarding_call_but_never_visited", None, get_volunteers_booked_onboarding_call_but_never_visited),
    FilterListEntry("users_require_prematching_call_not_booked", None, users_require_prematching_call_not_booked),
    FilterListEntry("users_with_booked_prematching_call", None, users_with_booked_prematching_call),
    FilterListEntry("users_with_booked_prematching_call_exclude_had", None, users_with_booked_prematching_call),
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
    FilterListEntry("journey_v2__user_created", None, user_created),
    FilterListEntry("journey_v2__never_active_or_deleted", None, never_active_or_deleted),
    FilterListEntry("journey_v2__email_verified", None, email_verified),
    FilterListEntry("journey_v2__user_form_completed", None, user_form_completed),
    FilterListEntry("journey_v2__booked_onboarding_call", None, booked_onboarding_call),
    FilterListEntry("journey_v2__first_search", None, first_search_v1),
    FilterListEntry("journey_v2__first_search_v2", None, first_search_v2),
    FilterListEntry("journey_v2__first_search_volunteers", None, first_search_volunteers),
    FilterListEntry("journey_v2__first_search_learners", None, first_search_learners),
    FilterListEntry("journey_v2__user_searching_again", None, user_searching),
    FilterListEntry("journey_v2__pre_matching", None, pre_matching),
    FilterListEntry("journey_v2__match_takeoff", None, match_takeoff),
    FilterListEntry("journey_v2__active_matching", None, active_match),
    FilterListEntry("journey_v2__ongoing_non_completed_match", None, ongoing_non_completed_match),
    FilterListEntry("journey_v2__never_active", None, never_active),
    FilterListEntry("journey_v2__no_show", None, no_show),
    FilterListEntry("journey_v2__user_ghosted", None, ghoster),
    FilterListEntry("journey_v2__no_confirm", None, no_confirm),
    FilterListEntry("journey_v2__failed_matching", None, failed_matching),
    FilterListEntry("journey_v2__happy_inactive", None, happy_inactive),
    FilterListEntry("journey_v2__happy_active", None, happy_active),
    FilterListEntry("journey_v2__too_low_german_level", None, too_low_german_level),
    FilterListEntry("journey_v2__unmatched", None, over_30_days_after_prematching_still_searching),
    FilterListEntry("journey_v2__gave_up_searching", None, gave_up_searching),
    FilterListEntry("journey_v2__user_deleted", None, user_deleted),
    FilterListEntry("journey_v2__marked_unresponsive", None, marked_unresponsive),
    FilterListEntry("journey_v2__never_active_or_deleted_or_created", None, never_active_or_deleted_or_created),
    FilterListEntry("journey_v2__email_verified_and_form_completed", None, email_verified_and_form_completed),
    FilterListEntry("journey_v2__email_not_verified_or_form_not_completed", None, email_not_verified_or_form_not_completed),
    FilterListEntry("journey_v2__not_too_low_german_level__is_onboarded", None, not_too_low_german_level__is_onboarded),
    FilterListEntry("journey_v2__too_low_german_level_or_not_onboarded", None, too_low_german_level_or_not_onboarded),
    FilterListEntry("needs_matching_volunteers", None, needs_matching_volunteers),
    FilterListEntry("herrduenschnlate", None, only_hd_test_user),
    FilterListEntry("community", None, community_calls),
    FilterListEntry("learners_with_a1a2", "Learners with A1/A2", learners_with_a1a2),
    FilterListEntry("learners_better_than_a1a2", "Learners with at least B1", learners_better_than_a1a2),
    FilterListEntry("community__learners_better_than_a1a2", "Commmunity and Learners with at least B1", community__learners_better_than_a1a2),
    FilterListEntry("community__6weeks__ehrenamtliche_und_lernende_with_a1a2", "(Community) Last 6 Weeks & Ehrenamtliche und Lernende with A1A2", community__ehrenamtliche_und_lernende_with_a1a2),
    #FilterListEntry("community__ehrenamtliche_und_lernende_with_a1a2", "Community-Call & Ehrenamtliche und Lernende with A1A2", community__ehrenamtliche_und_lernende_with_a1a2),
    FilterListEntry("newsletter_subscribed", None, subscribed_to_newsletter),
    FilterListEntry("completed_form__no__onboarding_call", None, completed_form__no__onboarding_call),
    FilterListEntry("completed_form__created_within_6months", None, completed_form__created_within_6months),
    FilterListEntry("completed_form__created_within_6months_no_onboarding_call", None, completed_form__created_within_6months_no_onboarding_call),
    FilterListEntry("completed_form__created_within_6months_no_onboarding_call_volunteer", None, completed_form__created_within_6months_no_onboarding_call_volunteer),
    FilterListEntry("TEST__all_volunteers_min_one_no_ongoing_match", None, all_volunteers_min_one_no_ongoing_match),
    FilterListEntry("EXTRA__volunteers_with_completed_match_no_ongoing", 
                    "Volunteers with at least one completed match and no ongoing matches", 
                    volunteers_with_completed_match_no_ongoing),
]

FILTER_LISTS = PANEL_V1_FILTER_LISTS + USER_JOURNEY_FILTER_LISTS


def get_dynamic_userlists() -> List[FilterListEntry]:
    return [
        FilterListEntry(":dyn:" + str(dyn_user_list.id), dyn_user_list.name)
        for dyn_user_list in DynamicUserList.objects.all()
    ]


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
