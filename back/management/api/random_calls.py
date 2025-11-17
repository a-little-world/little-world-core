import asyncio

from chat.models import Chat, ChatSerializer
from django.conf import settings
from django.db import transaction
from django.urls import path
from django.utils import timezone
from livekit import api as livekit_api
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from video.models import (
    LiveKitRoom,
    RandomCallLobby,
    RandomCallLobbyUser,
    RandomCallMatching,
    RandomCallSession,
)

from management.authentication import NativeOnlyJWTAuthentication
from management.models.matches import Match

# from management.tasks import kill_livekit_room


class AuthenticateRoomParams(serializers.Serializer):
    partner_id = serializers.CharField()


async def create_livekit_room(room_name):
    lkapi = livekit_api.LiveKitAPI(
        url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    results = await lkapi.room.list_rooms(livekit_api.ListRoomsRequest())
    print("Rooms:", results)
    if room_name not in [room.name for room in results.rooms]:
        room_info = await lkapi.room.create_room(
            livekit_api.CreateRoomRequest(name=room_name),
        )
        print("Created room that didn't exist:", room_name, room_info)
    await lkapi.aclose()


def get_partner(user):
    partner = RandomCallLobby.objects.filter(status=False).exclude(user=user).order_by("id")
    if partner.exists():
        partner = partner.first()
        while partner.status:
            partner = partner.delete()
            partner = partner.first()
        return partner
    else:
        return None


def get_users_to_pair(user):
    try:
        user_lobby = RandomCallLobby.objects.get(user=user)
        partner = get_partner(user)
        if partner is None:
            raise Exception("Partner does not exists yet")
        with transaction.atomic():
            if user_lobby.status:
                raise Exception("I am already matched!")
            user_lobby.status = True
            user_lobby.save()
            if partner.status:
                partner = None
            else:
                partner.status = True
                partner.save()
        return (user_lobby, partner)
    except Exception:
        return (user_lobby.user, None)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def authenticate_livekit_random_call(request):
    random_match = RandomCallMatching.objects.get(uuid=request.data["matchId"])

    print(random_match.u1, random_match.u2)

    temporary_chat = Chat.get_or_create_chat(random_match.u1, random_match.u2)
    temporary_room = LiveKitRoom.get_or_create_room(random_match.u1, random_match.u2)
    temporary_match = ""
    try:
        temporary_match = Match.get_random_match(random_match.u1, random_match.u2).first()
        if temporary_match is None:
            raise Exception("")
    except Exception:
        temporary_match = Match.objects.create(
            user1=random_match.u1, user2=random_match.u2, is_random_call_match=True, active=False
        )
    loop = asyncio.new_event_loop()
    loop.run_until_complete(create_livekit_room(str(temporary_room.uuid)))
    loop.close()
    token = (
        livekit_api.AccessToken(api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
        .with_identity(request.user.hash)
        .with_name(f"{request.user.profile.first_name} {request.user.profile.second_name[:1]}")
        .with_grants(
            livekit_api.VideoGrants(
                room_join=True,
                room=str(temporary_room.uuid),
            )
        )
        .to_jwt()
    )

    new_session = RandomCallSession.get_or_create(
        random_match=str(random_match.uuid), tmp_chat=temporary_chat, tmp_match=temporary_match, active=True
    )

    print("NEW SESSION:", new_session)

    # eta = new_session.end_time

    # kill_livekit_room.apply_async(
    #     (str(temporary_room.uuid), str(new_session.uuid), str(temporary_match.uuid), str(temporary_chat.uuid)), eta=eta
    # )

    return Response(
        {
            "token": str(token),
            "server_url": settings.LIVEKIT_URL,
            "chat": ChatSerializer(temporary_chat).data,
            "room": temporary_room.uuid,
            "random_match_id": str(random_match.uuid),
        }
    )


def is_lobby_active(lobby):
    if lobby.start_time > timezone.now():
        return False
    if lobby.end_time < timezone.now():
        return False
    return True


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def join_random_call_lobby(request, lobby_name="default"):
    # 1 - retrieve the lobby 'default' always for now
    lobby = RandomCallLobby.objects.get(name=lobby_name)
    if not is_lobby_active(lobby):
        return Response("Lobby is not active", status=400)
    # 2 - check if the user is already in the lobby
    user_in_lobby = RandomCallLobbyUser.objects.filter(user=request.user, lobby=lobby).exists()
    already_in_lobby = False
    if user_in_lobby:
        already_in_lobby = True
    # 3 - if the user is not in the lobby, add them to the lobby
    if not user_in_lobby:
        RandomCallLobbyUser.objects.create(user=request.user, lobby=lobby)
    # 4 - a-new user joined so start the celery task that performs the matching
    # TODO
    return Response({"lobby": lobby.uuid, "already_joined": already_in_lobby})


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def exit_random_call_lobby(request, lobby_name="default"):
    # 1 - retrieve the lobby
    lobby = RandomCallLobby.objects.get(name=lobby_name)
    if not is_lobby_active(lobby):
        return Response("Lobby is not active", status=400)
    # 2 - check if the user is in the lobby
    user_in_lobby = RandomCallLobbyUser.objects.filter(user=request.user, lobby=lobby)
    if not user_in_lobby.exists():
        return Response("You are not in the lobby", status=400)
    # 3 - remove the user from the lobby
    user_in_lobby.delete()
    # 4 TODO make 'cleanup'
    # - check if users had matches already, if so deactivate them
    # - for existing matches check if they where already in a session, if so deactivate them
    # TODO: also ensure if a user exists a-lobby another way, to mark him as 'offline' again and not consider anymore
    return Response("You have been removed from the lobby")


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def get_random_call_lobby_status(request, lobby_name="default"):
    # 1 - retrieve the lobby
    lobby = RandomCallLobby.objects.get(name=lobby_name)
    # 2 - check if the lobby is active
    if not is_lobby_active(lobby):
        return Response("Lobby is not active", status=400)
    # 3 - check if the user is in the lobby
    user_in_lobby = RandomCallLobbyUser.objects.filter(user=request.user, lobby=lobby)
    if not user_in_lobby.exists():
        return Response("You are not in the lobby", status=400)
    # 4 - check the users lobby status
    # TODO: check if there is a random call matcing for that user
    return Response({"lobby": lobby.uuid, "status": lobby.status})


@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def get_random_call_status(request, random_call_session_id):
    # 1 - retrieve the random call session
    random_call_session = RandomCallSession.objects.get(uuid=random_call_session_id)
    if not random_call_session.exists():
        return Response("Random call session does not exist", status=400)
    # 2 - check if the requesting user is part of the random call session
    user_in_random_call_session = RandomCallLobbyUser.objects.filter(
        user=request.user, random_call_session=random_call_session
    )
    if not user_in_random_call_session.exists():
        return Response("You are not part of the random call session", status=400)
    # 3 - check if the random call session is active
    if not random_call_session.active:
        return Response("Random call session is not active", status=400)
    # 4 - check the random call session status
    # TODO: calculate remaining time, and possibly other status events
    # TODO: or atleast pass a session end time of sorts
    return Response({"random_call_session": random_call_session.uuid, "status": random_call_session.status})


api_urls = [
    path("api/random_calls/lobby/<str:lobby_name>/join", join_random_call_lobby),
    path("api/random_calls/lobby/<str:lobby_name>/exit", exit_random_call_lobby),
    path("api/random_calls/lobby/<str:lobby_name>/status", get_random_call_lobby_status),
    # path("api/random_calls/get_token_random_call", authenticate_livekit_random_call),
]
