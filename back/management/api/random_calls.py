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
from django.db.models import Q

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

#TODO:useSWR auto fetch, websockets
@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def authenticate_livekit_random_call(request):
    #in_lobby = True if (RandomCallLobby.objects.filter(user=request.user).exists()) else False #checks if the given user is already in the Lobby DB and assign T/F
    lobby_user = RandomCallLobby.objects.filter(user=request.user).first()
    lobby_partner = RandomCallLobby.objects.exclude(Q(user=request.user) | Q(status=True)).order_by('?').first()
    partner = {"uuid": ""}
    try:
        partner = lobby_partner.user
        if lobby_user:
            partner = RandomCallMatchings.objects.filter(u2=request.user).first().u1
    except:
        print("No RandomCallMatching yet")
        
    if not lobby_user.status:
        lobby_partner.status = True
        lobby_partner.save()
        lobby_user.status = True
        lobby_user.save()

    temporary_chat = Chat.get_or_create_chat(request.user, partner)
    temporary_room = LiveKitRoom.get_or_create_room(request.user, partner)
    temporary_match = ""
    try:
        temporary_match = Match.get_match(request.user, partner).first()
        if temporary_match is None:
            raise Exception("")
    except:
        temporary_match = Match.objects.create(user1=request.user, user2=partner, is_random_call_match=True)

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

    RandomCallMatchings.objects.create(u1=request.user, u2=partner, tmp_chat=str(temporary_chat.uuid), tmp_match=str(temporary_match.uuid))
    
    return Response({"token": str(token), "server_url": settings.LIVEKIT_URL, "chat": ChatSerializer(temporary_chat).data, "room": temporary_room.uuid})

@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def join_random_call_lobby(request):
    lobby = RandomCallLobby.get_or_create_lobby(user=request.user)
    if lobby.status:
        lobby.status = False
        lobby.save()
    return Response({"lobby": lobby.uuid})

@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def exit_random_call_lobby(request):
    RandomCallLobby.objects.filter(user=request.user).delete()
    try:
        matchings = RandomCallMatchings.objects.filter(Q(u1=request.user) | Q(u2=request.user))
        for match in matchings:
            Chat.objects.filter(uuid=match.tmp_chat).delete()
    except Exception as e:
        print(e)
    return Response("SUCCESS")

@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_users_in_lobby(request):
    resp = serializers.serialize('json', RandomCallLobby.objects.all())
    print(resp)
    return Response(resp, safe=False)

api_urls = [
    path('api/random_calls/get_token_random_call', authenticate_livekit_random_call),
    path('api/random_calls/join_lobby', join_random_call_lobby),
    path('api/random_calls/exit_lobby', exit_random_call_lobby),
    path('api/random_calls/get_all_lobby', get_users_in_lobby),
]
