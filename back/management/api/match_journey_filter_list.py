from dataclasses import dataclass
from management.api.match_journey_filters import match_unviewed, match_one_user_viewed, match_confirmed_no_contact, match_confirmed_single_party_contact, match_first_contact, match_ongoing, match_free_play, completed_match, never_confirmed, no_contact, user_ghosted, contact_stopped, matching_proposals, expired_matching_proposals, all_matches, only_non_support_matching, reported_or_removed_match


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
    FilterListEntry("match_journey_v2__all", "All matches", all_matches),
    FilterListEntry("match_journey_v2__only_non_support_matching", "Matches that are not support matching.", only_non_support_matching),
    FilterListEntry("match_journey_v2__proposed_matches", "(Pre-Matching) Proposed matches [No real-matches yet]", matching_proposals),
    FilterListEntry("match_journey_v2__unviewed", "(Pre-Matching) Matches that are active and not yet confirmed by both users.", match_unviewed),
    FilterListEntry("match_journey_v2__one_user_viewed", "(Pre-Matching) Matches that are active, not yet confirmed by both users, but confirmed by at least one user.", match_one_user_viewed),
    FilterListEntry("match_journey_v2__confirmed_no_contact", "(Pre-Matching) Matches that are active, confirmed by both users, no unmatch reports, and neither user has sent messages or participated in video calls at all.", match_confirmed_no_contact),
    FilterListEntry("match_journey_v2__confirmed_single_party_contact", "(Pre-Matching) Matches that are active, confirmed, with one user having reported the unmatch or only one user having contacted the other.", match_confirmed_single_party_contact),
    FilterListEntry("match_journey_v2__first_contact", "(Ongoing-Matching) Matches where both users have either participated in the same video call or sent at least one message to each other.", match_first_contact),
    FilterListEntry("match_journey_v2__match_ongoing", "(Ongoing-Matching) Matches where users have exchanged multiple messages or video calls, their last message or video call is less than 14 days ago, and the match isn't older than the desired match duration.", match_ongoing),
    FilterListEntry("match_journey_v2__match_free_play", "(Ongoing-Matching) Matches that are over 10 weeks old and still active, also ensuring the match is still 'ongoing'.", match_free_play),
    FilterListEntry("match_journey_v2__completed_match", "(Finished-Matching) Matches that are over 10 weeks old, inactive, still in contact, and exchanged a desired number of messages and video calls.", completed_match),
    FilterListEntry("match_journey_v2__never_confirmed", "(Failed-Matching) Matches older than a specified number of days but still unconfirmed.", never_confirmed),
    FilterListEntry("match_journey_v2__no_contact", "(Failed-Matching) Matches that are confirmed but without contact and older than a specified number of days.", no_contact),
    FilterListEntry("match_journey_v2__user_ghosted", "(Failed-Matching) Matches that are confirmed, have a single party contact, and are older than a specified number of days.", user_ghosted),
    FilterListEntry("match_journey_v2__contact_stopped", "(Failed-Matching) Matches older than the desired match duration where users interacted but their interaction stopped before the desired duration.", contact_stopped),
    FilterListEntry("match_journey_v2__expired_proposals", "(Failed-Matching) Matches that are proposed but expired.", expired_matching_proposals),
    FilterListEntry("match_journey_v2__reported_or_removed", "(Failed-Matching) Reported or removed matches.", reported_or_removed_match)
]


def get_match_list_by_name(name):
    for element in MATCH_JOURNEY_FILTERS:
        if element.name == name:
            return element
    return None
