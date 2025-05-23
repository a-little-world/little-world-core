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
    user = User.objects.get(email="herrduenschnlate+1@gmail.com")
    partner = User.objects.get(hash=request.data["partner_id"])

    temporary_chat = Chat.objects.create(u1=user, u2=partner) #create temporary chat for the matched user
    chat = ChatSerializer(temporary_chat).data
    
    try:
        temporary_room = LiveKitRoom.get_room(user, partner)
        print(f"TEMPORARY ROOM: {temporary_room}")
    except:
        temporary_room = LiveKitRoom.objects.create(u1=user, u2=partner)

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

    return Response({"token": str(token), "server_url": settings.LIVEKIT_URL, "chat": chat})

@api_view(["POST"])
def join_random_call_lobby(request):
    user = User.objects.get(hash=request.data["userId"])
    lobby = RandomCallLobby.objects.create(user=user, status=False)
    print(f"LOBBY UUID:{lobby.uuid}")
    return Response(lobby.uuid)

@api_view(["POST"])
def exit_random_call_lobby(request):
    user = User.objects.get(hash=request.data["userId"])
    tmp = RandomCallLobby.objects.filter(user=user).delete()
    print(f"TMP: {tmp}")
    return Response("SUCCESS")

api_urls = [
    path('api/random_calls/allowed', get_prematch_status),
    path('api/random_calls/get_token_random_call', authenticate_livekit_random_call),
    path('api/random_calls/join_lobby', join_random_call_lobby),
    path('api/random_calls/exit_lobby', exit_random_call_lobby),
]
