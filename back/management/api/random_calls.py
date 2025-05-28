import asyncio
import json
import uuid
from datetime import timedelta

from chat.consumers.messages import InBlockIncomingCall, NewActiveCallRoom
from chat.models import Chat, ChatSerializer, Message
from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from livekit import api as livekit_api
from management.models.matches import Match
from management.models.post_call_review import PostCallReview
from management.models.user import User
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from translations import get_translation

from video.models import (
    LiveKitRoom,
    LivekitSession,
    LivekitWebhookEvent,
    SerializeLivekitSession,
    RandomCallLobby,
    RandomCallMatchings,
)

@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_prematch_status(request):
    user = request.user
    return Response(user.state.had_prematching_call)

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

@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def authenticate_livekit_random_call(request):
    user = User.objects.get(hash=request.data["userId"])
    in_lobby = True if (RandomCallLobby.is_in_lobby(user)) else False #checks if the given user is already in the Lobby DB and assign T/F

    partner = RandomCallLobby.objects.exclude(user=user).order_by('?').first().user #from the lobby a random user is selected, however in the future this selection logic must be more thoughtful
    temporary_chat = Chat.objects.create(u1=user, u2=partner) #the livekit token can be generated without a chat or room, however in the current setup of our backend, the partner user seems to be unable to load the livekitsession without these infos
    temporary_room = LiveKitRoom.get_or_create_room(user, partner)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(create_livekit_room(str(temporary_room.uuid)))
    loop.close()
    token = (
        livekit_api.AccessToken(api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
        .with_identity(user.hash)
        .with_name(f"{user.profile.first_name} {user.profile.second_name[:1]}")
        .with_grants(
            livekit_api.VideoGrants(
                room_join=True,
                room=str(temporary_room.uuid),
            )
        )
        .to_jwt()
    )
    
    RandomCallMatchings.get_or_create_match(user1=user, user2=partner)

    return Response({"token": str(token), "server_url": settings.LIVEKIT_URL, "chat": ChatSerializer(temporary_chat).data, "room": temporary_room.uuid})

@api_view(["POST"])
def join_random_call_lobby(request):
    user = User.objects.get(hash=request.data["userId"])
    lobby = RandomCallLobby.objects.create(user=user, status=False)
    return Response({"lobby": lobby.uuid})

@api_view(["POST"])
def exit_random_call_lobby(request):
    user = User.objects.get(hash=request.data["userId"])
    tmp = RandomCallLobby.objects.filter(user=user).delete()
    return Response("SUCCESS")

api_urls = [
    path('api/random_calls/allowed', get_prematch_status),
    path('api/random_calls/get_token_random_call', authenticate_livekit_random_call),
    path('api/random_calls/join_lobby', join_random_call_lobby),
    path('api/random_calls/exit_lobby', exit_random_call_lobby),
]
