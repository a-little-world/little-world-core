from typing import Optional, Tuple
import pgeocode
from django.db.models import Q

from patenmatch.models import PatenmatchUser, PatenmatchOrganization

MAX_CAPACITY = 5
MIN_CAPACITY = 1
CAPACITY_WEIGHT = 1.0
DISTANCE_WEIGHT = 10.0

def get_coordinates(postal_code: str) -> Optional[Tuple[float, float]]:
    """Get latitude and longitude from postal code."""
    try:
        nomi = pgeocode.Nominatim('de')
        location = nomi.query_postal_code(postal_code)
        if not location.empty and location['latitude'] and location['longitude']:
            return location['latitude'], location['longitude']
        return None
    except Exception:
        return None

def calculate_distance_score(user_postal: str, org_postal: str, max_distance: float) -> float:
    """Calculate normalized distance score (0 to 1)."""
    try:
        # here 'pgeocode' performs a web request apparently TODO why does it do that?
        dist = pgeocode.GeoDistance('de')
        distance = dist.query_postal_code(user_postal, org_postal)
        if distance is None:
            return 0.0
        
        normalized_score = 1.0 - min(distance, max_distance) / max_distance
        return max(0.0, normalized_score)
    except Exception:
        return 0.0

def calculate_capacity_score(capacity: int) -> float:
    """Calculate normalized capacity score (0 to 1)."""
    if capacity < MIN_CAPACITY or capacity > MAX_CAPACITY:
        return 0.0
    return (capacity - MIN_CAPACITY) / (MAX_CAPACITY - MIN_CAPACITY)

def calculate_total_score(distance_score: float, capacity_score: float) -> float:
    """Calculate weighted total score."""
    return (DISTANCE_WEIGHT * distance_score) + (CAPACITY_WEIGHT * capacity_score)

def find_organization_match(user: PatenmatchUser) -> Optional[PatenmatchOrganization]:
    """Find the best matching organization for a user."""
    # If user requested a specific organization, return it if valid
    if user.request_specific_organization:
        # TODO: handle this case differently
        return user.request_specific_organization

    # limit potential orgs TODO: optimize this more!
    organizations = PatenmatchOrganization.objects.filter(
        Q(target_groups__contains=user.support_for)
    ).exclude(
        matched_users__id=user.id
    )

    best_match = None
    best_score = -1

    # TODO: might get slow with too many orgs
    for org in organizations:
        distance_score = calculate_distance_score(
            user.postal_code,
            org.postal_code,
            float(org.maximum_distance)
        )

        if distance_score == 0:
            continue

        capacity_score = calculate_capacity_score(org.capacity)
        total_score = calculate_total_score(distance_score, capacity_score)

        if total_score > best_score:
            best_score = total_score
            best_match = org

    return best_match