import inspect
from dataclasses import dataclass

from management.api.match_journey_filters import (
    all_matches,
    completed_match,
    contact_stopped,
    expired_matching_proposals,
    failed_matches,
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
    ongoing_matches,
    only_non_support_matching,
    reported_or_removed_match,
    sucess_matches,
    support_matching,
    user_ghosted,
)
from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType

GITHUB_API_SOURCE_ROOT = "https://github.com/a-little-world/little-world-core/blob/main/back/management/api"


def get_queryset_source_reference(queryset: callable) -> dict:
    if queryset is None:
        return {"source_file": None, "source_line": None, "source_url": None}

    try:
        source_line = inspect.getsourcelines(queryset)[1]
    except (OSError, TypeError):
        source_line = None

    module_name = getattr(queryset, "__module__", "")
    source_file = f"back/{module_name.replace('.', '/')}.py" if module_name else None
    source_url = None
    if source_file and source_line and source_file.startswith("back/management/api/"):
        source_url = f"{GITHUB_API_SOURCE_ROOT}/{source_file.removeprefix('back/management/api/')}#L{source_line}"

    return {"source_file": source_file, "source_line": source_line, "source_url": source_url}


@dataclass
class FilterListEntry:
    name: str
    description: str | None
    queryset: callable = None

    def to_dict(self):
        description = self.description
        if description is None and self.queryset and self.queryset.__doc__:
            description = self.queryset.__doc__.strip()
        source_reference = get_queryset_source_reference(self.queryset)
        return {
            "name": self.name,
            "description": description,
            **source_reference,
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


def get_match_bucket_label(bucket_name: str | None) -> str:
    if not bucket_name:
        return "Unknown"

    if bucket_name == "unknown":
        return "Unknown"

    slug = bucket_name.split("__")[-1]
    return slug.replace("_", " ").strip().title()


def determine_match_bucket(match_pk):
    try:
        match_categorie_buckets = [
            "special__support_matching",
            "match_journey_v2__unviewed",
            "match_journey_v2__one_user_viewed",
            "match_journey_v2__confirmed_no_contact",
            "match_journey_v2__confirmed_single_party_contact",
            "match_journey_v2__first_contact",
            "match_journey_v2__match_ongoing",
            "match_journey_v2__completed_match",
            "match_journey_v2__match_free_play",
            "match_journey_v2__never_confirmed",
            "match_journey_v2__no_contact",
            "match_journey_v2__user_ghosted",
            "match_journey_v2__contact_stopped",
            "match_journey_v2__reported_or_removed",
        ]
        bucket_map = {entry.name: entry for entry in MATCH_JOURNEY_FILTERS if entry.name in match_categorie_buckets}
        for bucket in match_categorie_buckets:
            if bucket_map[bucket].queryset(Match.objects.filter(pk=match_pk, match_type=MatchType.STANDARD)).exists():
                return bucket
        return None
    except Exception as e:
        print(e)
        return None
