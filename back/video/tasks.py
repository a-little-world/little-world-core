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

    # 0 - cleanup inactive lobby users TODO
    lobby_users = RandomCallLobbyUser.objects.filter(
        lobby=lobby, is_active=False, last_status_checked_at__lt=timezone.now() - timedelta(seconds=10)
    )
    lobby_users.update(is_active=False, last_status_checked_at=timezone.now())

    # 2 - check if the lobby is active
    if not is_lobby_active(lobby):
        raise Exception("Lobby is not active")
    # 3 - retrieve all users in the lobby
    # Filter out users for which a non processed random call matching exists
    active_matchings = RandomCallMatching.objects.filter(lobby=lobby, accepted=False, rejected=False)
    matched_u1 = active_matchings.values_list("u1_id", flat=True)
    matched_u2 = active_matchings.values_list("u2_id", flat=True)

    # TODO: possibly add something that helps ensuring a certain two user pair is not matched twice ( if possible )
    users_in_lobby = (
        RandomCallLobbyUser.objects.filter(lobby=lobby, is_active=True)
        .exclude(user_id__in=matched_u1)
        .exclude(user_id__in=matched_u2)
    )
    # 4 - gather all user id's and select random pairs
    user_ids = list(users_in_lobby.values_list("user_id", flat=True))
    if len(user_ids) < 2:
        return {"matchings": []}
    pair = random.sample(user_ids, 2)
    # 5 - create a new random call matches
    random_match = RandomCallMatching.objects.create(u1_id=pair[0], u2_id=pair[1], lobby=lobby)
    # 6 - For every match start a 'cleanup_if_not_accepted' task that runs 30s after the match is created
    cleanup_if_not_accepted.apply_async(args=[random_match.uuid], countdown=30)
    return {"matchings": [pair]}


def cleanup_if_not_accepted(match_uuid):
    # 1 - retrieve the match
    match = RandomCallMatching.objects.get(uuid=match_uuid)
    auto_rejected_match = False
    if not (match.accepted or match.rejected):
        # 2 - auto reject the match
        auto_rejected_match = True
        match.rejected = True
        match.save()
    # TODO: websocket event for this change!
    return {"match_uuid": match_uuid, "auto_rejected_match": auto_rejected_match}


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
