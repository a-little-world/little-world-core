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
from django.db import transaction
from management.tasks import kill_livekit_room



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

def get_random_user_pair(user):
    with transaction.atomic():
        try:
            user_lobby = RandomCallLobby.objects.select_for_update(skip_locked=True).get(user=user, status=False)
            print(f"I am {user_lobby.user}")
        except RandomCallLobby.DoesNotExist:
            return (None, None)

        partner = RandomCallLobby.objects.select_for_update(skip_locked=True).filter(status=False).exclude(user=user).order_by('id').first()
        print(f"I am {user_lobby.user} and found {partner.user}")
        if not partner:
            return (None, None)

        user_lobby.status = True
        partner.status = True
        user_lobby.save()
        partner.save()

        return (user_lobby.user, partner.user)

@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def authenticate_livekit_random_call(request):

    lobby_user, partner = get_random_user_pair(request.user)

    if lobby_user is None or partner is None:
        random_match = RandomCallMatchings.objects.filter(Q(u1=request.user) | Q(u2=request.user)).exclude(active=False).first()
        if random_match:
            lobby_user = request.user
            partner = random_match.u1 if random_match.u2 == request.user else random_match.u2
            print(f"I am {lobby_user} and already in an active match with {partner}")

    temporary_chat = Chat.get_or_create_chat(lobby_user, partner)
    temporary_room = LiveKitRoom.get_or_create_room(lobby_user, partner)
    temporary_match = ""
    try:
        temporary_match = Match.get_match(lobby_user, partner).first()
        if temporary_match is None:
            raise Exception("")
    except:
        temporary_match = Match.objects.create(user1=lobby_user, user2=partner, is_random_call_match=True)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(create_livekit_room(str(temporary_room.uuid)))
    loop.close()
    token = (
        livekit_api.AccessToken(api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
        .with_identity(lobby_user.hash)
        .with_name(f"{lobby_user.profile.first_name} {lobby_user.profile.second_name[:1]}")
        .with_grants(
            livekit_api.VideoGrants(
                room_join=True,
                room=str(temporary_room.uuid),
            )
        )
        .to_jwt()
    )
    RandomCallMatchings.get_or_create_match(user1=lobby_user, user2=partner, tmp_chat=str(temporary_chat.uuid), tmp_match=str(temporary_match.uuid), active=True)
    
    from datetime import datetime, timedelta, timezone
    eta = datetime.now(timezone.utc) + timedelta(seconds=30)
    kill_livekit_room.apply_async(
        (temporary_room.uuid,),
        eta=eta
        )
    
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
            match.active=False
            match.save()
            Chat.objects.filter(uuid=match.tmp_chat).delete()
    except Exception as e:
        print(e)
    return Response("SUCCESS")

@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_random_call_status(request, random_match_id):
    random_match_exists = RandomCallMatchings.objects.filter(
        Q(uuid=random_match_id) & (Q(u1=request.user) | Q(u2=request.user))
    ).exists()
    if not random_match_exists:
        return Response({
            "exists": False,
            "completed": True,
            "remaining_time": 0.0
        })
    
    random_match = RandomCallMatchings.objects.get(
        Q(uuid=random_match_id) & (Q(u1=request.user) | Q(u2=request.user))
    )
    
    completed = random_match.end_time is not None
    
    remaining_time = 0.0
    
    if not completed:
        call_start_time = random_match.created_at
        current_time = timezone.now()
        elapsed_time = (current_time - call_start_time).total_seconds()
        
        if random_match.end_time:
            total_duration = (random_match.end_time - call_start_time).total_seconds()
            remaining_time = max(0.0, total_duration - elapsed_time)
        else:
            remaining_time = float('inf')
    else:
        remaining_time = 0.0
    
    return Response({
        "exists": True,
        "completed": completed,
        "remaining_time": remaining_time
    })

api_urls = [
    path('api/random_calls/get_token_random_call', authenticate_livekit_random_call),
    path('api/random_calls/join_lobby', join_random_call_lobby),
    path('api/random_calls/exit_lobby', exit_random_call_lobby),
    path('api/random_calls/status/<uuid:random_match_id>', get_random_call_status),
]
