import random
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching
from video.services.livekit_session_correction import process_unusually_long_sessions


@shared_task(name="video.tasks.daily_fix_unusually_long_livekit_sessions")
def daily_fix_unusually_long_livekit_sessions(cutoff_hours: float = 4.0):
    """
    Runs daily to cap unusually long sessions for records aged between 24 and 60 hours.
    """
    # 24h <= age < 60h window
    result = process_unusually_long_sessions(
        cutoff_hours=cutoff_hours,
        min_age_hours=24.0,
        max_age_hours=60.0,
        dry_run=False,
    )
    return result


@shared_task(name="video.tasks.random_call_lobby_perform_matching")
def random_call_lobby_perform_matching(lobby_name="default"):
    # Import here to avoid circular import
    from video.random_calls import is_lobby_active

    # TODO: add locking mechanism that assures this tasks only runs once in parallel!
    # 1 - retrieve the lobby
    lobby = RandomCallLobby.objects.get(name=lobby_name)
    # 2 - check if the lobby is active
    if not is_lobby_active(lobby):
        raise Exception("Lobby is not active")
    # 3 - retrieve all users in the lobby
    # Filter out users for which a non processed random call matching exists
    active_matchings = RandomCallMatching.objects.filter(
        lobby=lobby, accepted=False, rejected=False
    )
    matched_u1 = active_matchings.values_list("u1_id", flat=True)
    matched_u2 = active_matchings.values_list("u2_id", flat=True)
    
    users_in_lobby = RandomCallLobbyUser.objects.filter(lobby=lobby, is_active=True).exclude(
        user_id__in=matched_u1
    ).exclude(
        user_id__in=matched_u2
    )
    # 4 - gather all user id's and select random pairs
    user_ids = list(users_in_lobby.values_list("user_id", flat=True))
    if len(user_ids) < 2:
        return {"matchings": []}
    pair = random.sample(user_ids, 2)
    # 5 - create a new random call matches
    RandomCallMatching.objects.create(u1_id=pair[0], u2_id=pair[1], lobby=lobby)
    return {"matchings": [pair]}


@shared_task(name="video.tasks.create_default_random_call_lobby")
def create_default_random_call_lobby():
    # create a new random call lobby
    existing_lobby = RandomCallLobby.objects.filter(name="default").exists()
    if existing_lobby:
        return {"lobby": "default"}
    lobby = RandomCallLobby.objects.create(name="default")
    lobby.start_time = timezone.now()
    lobby.end_time = timezone.now() + timedelta(days=1)
    lobby.save()
    return {"lobby": "default"}
