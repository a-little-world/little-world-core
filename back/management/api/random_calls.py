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
    RandomCallSession,
    SerializeLivekitSession,
    RandomCallLobby,
    RandomCallMatching,
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


def get_users_to_pair(user):
    with transaction.atomic():
        try:
            user_lobby = RandomCallLobby.objects.select_for_update(skip_locked=True).get(user=user)
            partner = RandomCallLobby.objects.select_for_update(skip_locked=True).filter(status=False).exclude(user=user).order_by('id')
            if partner.exists():
                partner = partner.first()
            else:
                raise Exception("Partner does not exists yet")

            user_lobby.status = True
            partner.status = True
            user_lobby.save()
            partner.save()

            return (user_lobby, partner)

        except Exception as e:
            return (user_lobby.user, None)

@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def match_random_pair(request):

    user_lobby, partner = get_users_to_pair(request.user)

    if partner is None:
        existing_match = RandomCallMatching.objects.filter(Q(u1=user_lobby) | Q(u2=user_lobby)).exclude(active=False)
        if existing_match.exists():
            return Response({"new_match": str(existing_match.first().uuid)})
        else:
            return Response("Currently Match not possible", status=500)

    new_match = RandomCallMatching.get_or_create_match(user1 = user_lobby.user, user2 = partner.user)
    print("newmatchuuid",new_match.uuid)
    return Response({"new_match": str(new_match.uuid)})

@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def authenticate_livekit_random_call(request):

    random_match = RandomCallMatching.objects.get(uuid = request.data["matchId"])

    print(random_match.u1, random_match.u2)

    temporary_chat = Chat.get_or_create_chat(random_match.u1, random_match.u2)
    temporary_room = LiveKitRoom.get_or_create_room(random_match.u1, random_match.u2)
    temporary_match = ""
    try:
        temporary_match = Match.get_match(random_match.u1, random_match.u2).first()
        if temporary_match is None:
            raise Exception("")
    except:
        temporary_match = Match.objects.create(user1=random_match.u1, user2=random_match.u2, is_random_call_match=True)
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
    
    from datetime import datetime, timedelta, timezone
    eta = datetime.now(timezone.utc) + timedelta(seconds=30)
    kill_livekit_room.apply_async(
        (temporary_room.uuid,),
        eta=eta
        )
    
    new_session = RandomCallSession.get_or_create(
        random_match=str(random_match.uuid),
        tmp_chat=temporary_chat,
        tmp_match=temporary_match,
        active=True
        )
    
    print("NEW SESSION:", new_session)

    return Response({
        "token": str(token),
        "server_url": settings.LIVEKIT_URL,
        "chat": ChatSerializer(temporary_chat).data,
        "room": temporary_room.uuid,
        "random_match_id": str(random_match.uuid)
    })

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
        matchings = RandomCallMatching.objects.filter(Q(u1=request.user) | Q(u2=request.user))
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
    print("ARRIVED IN CALL STATUS")
    random_match_exists = RandomCallSession.objects.filter(random_match=random_match_id).exists()
    if not random_match_exists:
        return Response({
            "exists": False,
            "completed": True,
            "remaining_time": 0.0
        })
    
    random_match = RandomCallSession.objects.get(random_match=random_match_id)
    
    completed = timezone.now() > random_match.end_time
    remaining_time = 0.0
    if not completed:
        if random_match.end_time:
            current_time = timezone.now()
            remaining_time = max(0.0, (random_match.end_time - current_time).total_seconds())
        else:
            remaining_time = 999999.0
    else:
        remaining_time = 0.0
    
    return Response({
        "exists": True,
        "completed": completed,
        "remaining_time": remaining_time
    })

@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def reset_match(request):
    match = RandomCallMatching.objects.filter(uuid=str(request.data["matchId"]))
    if match.exists():
        match = match.first()
        match.active = False
        match.save()
    else:
        return Response("ERROR while deactivating Random Match", status=500)
    sessions = RandomCallSession.objects.filter(random_match=str(request.data["matchId"]))
    if sessions.exists():
        for s in sessions:
            s.active = False
            s.save()
    else:
        return Response("ERROR while deactivating Random Session", status=500)
    return Response("All good", status=200)
    

api_urls = [
    path('api/random_calls/get_token_random_call', authenticate_livekit_random_call),
    path('api/random_calls/join_lobby', join_random_call_lobby),
    path('api/random_calls/exit_lobby', exit_random_call_lobby),
    path('api/random_calls/status/<uuid:random_match_id>', get_random_call_status),
    path('api/random_calls/match_random_pair', match_random_pair),
    path('api/random_calls/reset_match', reset_match),
]
