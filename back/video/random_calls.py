import asyncio

from chat.models import Chat, ChatSerializer
from django.conf import settings
from django.db.models import Q
from django.urls import path
from django.utils import timezone
from livekit import api as livekit_api
from management.authentication import NativeOnlyJWTAuthentication
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
from video.tasks import random_call_lobby_perform_matching

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
    random_call_lobby_perform_matching.apply_async(args=[lobby_name])
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
    response_data = {
        "lobby": lobby.uuid,
        "status": lobby.status,
        "matching": None,
    }
    # 4 - check the users lobby status
    random_call_matching = RandomCallMatching.objects.filter(
        Q(u1=request.user) | Q(u2=request.user), lobby=lobby, is_processed=False
    )
    matching = random_call_matching.first()
    has_matching = random_call_matching.exists()
    if has_matching:
        own_number = 1 if (matching.u1 == request.user) else 2

        matching_info = {
            "uuid": matching.uuid,
            "accepted": matching.u2_accepted if own_number == 1 else matching.u1_accepted,
        }

        response_data["matching"] = matching_info
    return Response(response_data)


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
    return Response({"random_call_session": str(random_call_session.uuid), "status": random_call_session.status})


@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def authenticate_random_call_match_livekit_room(request, lobby_name, match_uuid):
    # 1 - retrieve the lobby
    lobby = RandomCallLobby.objects.get(name=lobby_name)
    if not is_lobby_active(lobby):
        return Response("Lobby is not active", status=400)
    # 2 - retrieve the match
    match = RandomCallMatching.objects.get(uuid=match_uuid)
    if not match.exists():
        return Response("Match does not exist", status=400)
    # 3 - check if user is part of lobby
    user_in_lobby = RandomCallLobbyUser.objects.filter(user=request.user, lobby=lobby)
    if not user_in_lobby.exists():
        return Response("You are not part of the lobby", status=400)
    # 4 - check if match is processed
    if not match.is_processed:
        return Response("Match is not processed", status=400)
    # 5 - check if the user is part of this matching
    if not (match.u1 == request.user or match.u2 == request.user):
        return Response("You are not part of this matching", status=400)
    # 6 - check if both users accepted the matching
    if not (match.u1_accepted and match.u2_accepted):
        return Response("Both users must accept the matching", status=400)
    # 7 - Start actual room authentication
    temporary_chat = Chat.get_or_create_chat(match.u1, match.u2)
    # TODO: possible double room creating here! TODO: maybe move this directly to matching?
    temporary_room = LiveKitRoom.objects.get(u1=match.u1, u2=match.u2, random_call_room=True)
    if not temporary_room.exists():
        temporary_room = LiveKitRoom.objects.create(u1=match.u1, u2=match.u2, random_call_room=True)

    # TODO: @sugsoo created a temporary 'Match' object here this should be avoided instead the chats and message filter should allow random call matches?
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
    # TODO @sungsso create a random call session object here, we would like to be able to tag a 'LiveKitSession' as random call session instead
    return Response(
        {
            "token": str(token),
            "server_url": settings.LIVEKIT_URL,
            "chat": ChatSerializer(temporary_chat).data,
            "room": temporary_room.uuid,
            "random_match_id": str(match.uuid),
        }
    )


api_urls = [
    path("api/random_calls/lobby/<str:lobby_name>/join", join_random_call_lobby),
    path("api/random_calls/lobby/<str:lobby_name>/exit", exit_random_call_lobby),
    path("api/random_calls/lobby/<str:lobby_name>/status", get_random_call_lobby_status),
    path(
        "api/random_calls/lobby/<str:lobby_name>/match/<str:match_uuid>/room_authenticate",
        authenticate_random_call_match_livekit_room,
    ),
    # path("api/random_calls/get_token_random_call", authenticate_livekit_random_call),
]
