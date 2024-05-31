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
]
