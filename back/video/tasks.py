import random

from celery import shared_task

from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching
from video.random_calls import is_lobby_active
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
    # TODO: add locking mechanism that assures this tasks only runs once in parallel!
    # 1 - retrieve the lobby
    lobby = RandomCallLobby.objects.get(name=lobby_name)
    # 2 - check if the lobby is active
    if not is_lobby_active(lobby):
        raise Exception("Lobby is not active")
    # 3 - retrieve all users in the lobby
    # TODO: we need to filter out user for which a non processed random call matching exists
    users_in_lobby = RandomCallLobbyUser.objects.filter(lobby=lobby)
    # 4 - gather all user id's and select random pairs
    user_ids = users_in_lobby.values_list("user_id", flat=True)
    random_pairs = random.sample(user_ids, 2)
    # 5 - create a new random call matches
    for pair in random_pairs:
        RandomCallMatching.objects.create(u1=pair[0], u2=pair[1])
    return {"matchings": random_pairs}
