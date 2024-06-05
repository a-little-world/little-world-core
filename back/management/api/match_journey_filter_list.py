from dataclasses import dataclass
from management.api.match_journey_filters import (
    match_unviewed,
    match_one_user_viewed,
    match_confirmed_no_contact,
    match_confirmed_single_party_contact,
    match_first_contact,
    match_ongoing,
    match_free_play,
    completed_match,
    never_confirmed,
    no_contact,
    user_ghosted,
    contact_stopped
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

MATCH_JOURNEY_FILTERS = [
    FilterListEntry(
        "match_unviewed",
        "Match Journey: Matches that are active and not yet confirmed by both users.",
        match_unviewed
    ),
    FilterListEntry(
        "match_one_user_viewed",
        "Match Journey: Matches that are active, not yet confirmed by both users, but confirmed by at least one user.",
        match_one_user_viewed
    ),
    FilterListEntry(
        "match_confirmed_no_contact",
        "Match Journey: Matches that are active, confirmed by both users, no unmatch reports, and neither user has sent messages or participated in video calls at all.",
        match_confirmed_no_contact
    ),
    FilterListEntry(
        "match_confirmed_single_party_contact",
        "Match Journey: Matches that are active, confirmed, with one user having reported the unmatch or only one user having contacted the other.",
        match_confirmed_single_party_contact
    ),
    FilterListEntry(
        "match_first_contact",
        "Match Journey: Matches where both users have either participated in the same video call or sent at least one message to each other.",
        match_first_contact
    ),
    FilterListEntry(
        "match_ongoing",
        "Match Journey: Matches where users have exchanged multiple messages or video calls, their last message or video call is less than 14 days ago, and the match isn't older than the desired match duration.",
        match_ongoing
    ),
    FilterListEntry(
        "match_free_play",
        "Match Journey: Matches that are over 10 weeks old and still active, also ensuring the match is still 'ongoing'.",
        match_free_play
    ),
    FilterListEntry(
        "completed_match",
        "Match Journey: Matches that are over 10 weeks old, inactive, still in contact, and exchanged a desired number of messages and video calls.",
        completed_match
    ),
    FilterListEntry(
        "never_confirmed",
        "Match Journey: Matches older than a specified number of days but still unconfirmed.",
        never_confirmed
    ),
    FilterListEntry(
        "no_contact",
        "Match Journey: Matches that are confirmed but without contact and older than a specified number of days.",
        no_contact
    ),
    FilterListEntry(
        "user_ghosted",
        "Match Journey: Matches that are confirmed, have a single party contact, and are older than a specified number of days.",
        user_ghosted
    ),
    FilterListEntry(
        "contact_stopped",
        "Match Journey: Matches older than the desired match duration where users interacted but their interaction stopped before the desired duration.",
        contact_stopped
    )
]