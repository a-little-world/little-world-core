"""
Handler for twilio video room authentication
This takes care of
- creating / deleting video rooms ( they are stored in models.rooms.Room )
- authenticating video rooms
- completing rooms ( marking them as completed, when both parties disconnect )
"""
from twilio.rest import Client
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VideoGrant
from django.conf import settings


def _get_client():
    return Client(settings.TWILIO_API_KEY_SID, settings.TWILIO_API_SECRET)


def _get_status_url():
    callback_url = settings.BASE_URL + "/api/video_rooms/twillio_callback/"
    return callback_url


def _get_token(identity):
    # ttl (time-to-live is set to 14400 seconds (4hours) for now the maximal possible time. This is for cases
    # of connection interruption etc. May be reduced if we decide to limit call durations.
    return AccessToken(settings.TWILIO_ACCOUNT_SID,
                       settings.TWILIO_API_KEY_SID,
                       settings.TWILIO_API_SECRET,
                       identity=identity, ttl=14400)


def make_room(name):
    """
    Creates a twilio room 
    the status_callback_url is where twilio make callback api calls to
    """
    client = _get_client()
    room_type = 'go'  # TODO: we can have max 245 of these
    try:
        client.video.rooms.create(unique_name=name,
                                  type=room_type,
                                  media_region='de1',
                                  status_callback=_get_status_url())
    except Exception as e:
        print(e)


def complete_room(name):
    client = _get_client()
    client.video.rooms(name).update(status='completed')


def complete_room_if_empty(name):
    room = get_rooms(name)[0]
    participants = room.participants.list(status='connected')
    if len(participants) == 0:
        complete_room(name)


def get_rooms(name):
    client = _get_client()
    return client.video.rooms.list(unique_name=name)


def room_exists(name):
    rooms = get_rooms(name)
    return len(rooms) >= 1


def get_room_or_create(name):
    if not room_exists(name):
        make_room(name)
    return get_rooms(name)


def get_usr_auth_token(room_name, user_identity):
    token = _get_token(user_identity)
    # Create a Video grant and add to token
    video_grant = VideoGrant(room=room_name)
    token.add_grant(video_grant)
    return token.to_jwt()
