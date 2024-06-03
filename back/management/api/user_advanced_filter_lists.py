from dataclasses import dataclass
from management.api.user_advanced_filter import (
    all_users,
    users_that_are_searching_but_have_no_proposal,
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
    users_require_prematching_call_not_booked
)
from management.api.user_journey_filters import (
    user_created,
    email_verified,
    user_form_completed,
    booked_onboarding_call,
    first_search,
    user_searching,
    pre_matching,
    match_takeoff,
    never_active,
    no_show,
    ghoster,
    no_confirm,
    happy_inactive,
    too_low_german_level,
    unmatched,
    gave_up_searching
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

FILTER_LISTS = [
    FilterListEntry(
        "all",
        "All users ordered by date joined!",
        all_users
    ),
    FilterListEntry(
        "searching",
        "Users who are searching for a match! Exclude users that have not finished the user form or verified their email!",
        searching_users
    ),
    FilterListEntry(
        "needs_matching",
        "All users in 'searching' without any user that has an open proposal!",
        users_that_are_searching_but_have_no_proposal
    ),
    FilterListEntry(
        "in_registration",
        "Users who have not finished the user form or verified their email!",
        users_in_registration
    ),
    FilterListEntry(
        "active_within_3weeks",
        "Users who have been active within the last 3 weeks!",
        active_within_3weeks
    ),
    FilterListEntry(
        "active_match",
        "Users who have communicated with their match in the last 4 weeks",
        get_active_match_query_set
    ),
    FilterListEntry(
        "highquality_matching",
        "Users who have at least one matching with 20+ Messages",
        get_quality_match_query_set
    ),
    FilterListEntry(
        "message_reply_required",
        "Users who have an unread message to the admin user",
        get_user_with_message_to_admin
    ),
    FilterListEntry(
        "read_message_but_not_replied",
        "Read messages to the management user that have not been replied to",
        get_user_with_message_to_admin_that_are_read_but_not_replied
    ),
    FilterListEntry(
        "users_with_open_tasks",
        "Users who have open tasks",
        users_with_open_tasks
    ),
    FilterListEntry(
        "users_with_open_proposals",
        "Users who have open proposals",
        users_with_open_proposals
    ),
    FilterListEntry(
        "users_require_prematching_call_not_booked",
        "Users that still require a pre-matching call before matching, but haven't booked one yet",
        users_require_prematching_call_not_booked
    ),
    FilterListEntry(
        "users_with_booked_prematching_call",
        "Users that have booked a pre-matching call",
        users_with_booked_prematching_call
    ),
    FilterListEntry(
        "users_with_booked_prematching_call_exclude_had",
        "Users that have booked a pre-matching call but have not had one yet",
        users_with_booked_prematching_call
    ),
    FilterListEntry(
        "ujv2_user_created",
        "User Journey V2: User was created, but still has to verify mail, fill form and have a prematching call",
        user_created
    ),
    FilterListEntry(
        "ujv2_email_verified",
        "User Journey V2: User has verified email, but still has to fill form and have a prematching call",
        email_verified
    ),
    FilterListEntry(
        "ujv2_user_form_completed",
        "User Journey V2: User has filled form, but still has to have a prematching call",
        user_form_completed
    ),
    FilterListEntry(
        "ujv2_booked_onboarding_call",
        "User Journey V2: User has filled form and booked onboarding call",
        booked_onboarding_call
    ),
    FilterListEntry(
        "ujv2_first_search",
        "User Journey V2: User is doing first search i.e.: has no 'non-support' match",
        first_search
    ),
    FilterListEntry(
        "ujv2_user_searching",
        "User Journey V2: User is searching and has at least one match",
        user_searching
    ),
    FilterListEntry(
        "ujv2_pre_matching",
        "User Journey V2: User has `Pre-Matching` or `Kickoff-Matching` Match.",
        pre_matching
    ),
    FilterListEntry(
        "ujv2_match_takeoff",
        "User Journey V2: User has `Pre-Matching` or `Kickoff-Matching` Match.",
        match_takeoff
    ),
    FilterListEntry(
        "ujv2_never_active",
        "User Journey V2: Didn't ever become active",
        never_active
    ),
    FilterListEntry(
        "ujv2_no_show",
        "User Journey V2: Didn't show up to onboarding call",
        no_show
    ),
    FilterListEntry(
        "ujv2_ghoster",
        "User Journey V2: User has matching in [3.G] 'ghosted' his match",
        ghoster
    ),
    FilterListEntry(
        "ujv2_no_confirm",
        "User Journey V2: Learner that has matching in 'Never Confirmed'",
        no_confirm
    ),
    FilterListEntry(
        "ujv2_happy_inactive",
        "User Journey V2: Not searching, 1 or more matches at least one match in 'Completed Matching'",
        happy_inactive
    ),
    FilterListEntry(
        "ujv2_too_low_german_level",
        "User Journey V2: User never active, but was flagged with a 'state.to_low_german_level=True'",
        too_low_german_level
    ),
    FilterListEntry(
        "ujv2_unmatched",
        "User Journey V2: 'first-search' for over XX days, we failed to match the user at all",
        unmatched
    ),
    FilterListEntry(
        "ujv2_gave_up_searching",
        "User Journey V2: User that's `searching=False` and has 0 matches",
        gave_up_searching
    )
]