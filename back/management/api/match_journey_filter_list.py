from dataclasses import dataclass

from management.api.match_journey_filters import (
    all_matches,
    support_matching,
    completed_match,
    contact_stopped,
    expired_matching_proposals,
    match_completed_off_plattform,
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
    only_non_support_matching,
    reported_or_removed_match,
    user_ghosted,
    sucess_matches,
    ongoing_matches,
    failed_matches,
)


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


MATCH_JOURNEY_FILTERS = [
    FilterListEntry("match_journey_v2__all", None, all_matches),
    FilterListEntry(
        "match_journey_v2__only_non_support_matching",
        None,
        only_non_support_matching,
    ),
    FilterListEntry(
        "match_journey_v2__proposed_matches",
        None,
        matching_proposals,
    ),
    FilterListEntry(
        "match_journey_v2__unviewed",
        None,
        match_unviewed,
    ),
    FilterListEntry(
        "match_journey_v2__one_user_viewed",
        None,
        match_one_user_viewed,
    ),
    FilterListEntry(
        "match_journey_v2__confirmed_no_contact",
        None,
        match_confirmed_no_contact,
    ),
    FilterListEntry(
        "match_journey_v2__confirmed_single_party_contact",
        None,
        match_confirmed_single_party_contact,
    ),
    FilterListEntry(
        "match_journey_v2__first_contact",
        None,
        match_first_contact,
    ),
    FilterListEntry(
        "match_journey_v2__match_ongoing",
        None,
        match_ongoing,
    ),
    FilterListEntry(
        "match_journey_v2__match_free_play",
        None,
        match_free_play,
    ),
    FilterListEntry(
        "match_journey_v2__completed_match",
        None,
        completed_match,
    ),
    FilterListEntry(
        "match_journey_v2__never_confirmed",
        None,
        never_confirmed,
    ),
    FilterListEntry(
        "match_journey_v2__no_contact",
        None,
        no_contact,
    ),
    FilterListEntry(
        "match_journey_v2__user_ghosted",
        None,
        user_ghosted,
    ),
    FilterListEntry(
        "match_journey_v2__contact_stopped",
        None,
        contact_stopped,
    ),
    FilterListEntry(
        "match_journey_v2__expired_proposals",
        None,
        expired_matching_proposals,
    ),
    FilterListEntry(
        "match_journey_v2__reported_or_removed",
        None,
        reported_or_removed_match,
    ),
    FilterListEntry(
        "match_journey_v2__sucess_matches",
        None,
        sucess_matches,
    ),
    FilterListEntry(
        "match_journey_v2__ongoing_matches",
        None,
        ongoing_matches,
    ),
    FilterListEntry(
        "match_journey_v2__failed_matches",
        None,
        failed_matches,
    ),
    FilterListEntry(
        "all",
        None,
        all_matches,
    ),
    FilterListEntry(
        "match_completed_off_plattform",
        None,
        match_completed_off_plattform,
    ),
    FilterListEntry(
        "special__support_matching",
        None,
        support_matching,
    ),
]

def get_match_list_by_name(name):
    for element in MATCH_JOURNEY_FILTERS:
        if element.name == name:
            return element
    return None
