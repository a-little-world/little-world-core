from rest_framework.decorators import api_view, permission_classes, authentication_classes
from chat.models import Chat, ChatSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from video.models import LiveKitRoom, LivekitSession, LivekitWebhookEvent, SerializeLivekitSession
from management.models.user import User
from rest_framework.response import Response
from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from livekit import api as livekit_api
from django.urls import path
from drf_spectacular.utils import extend_schema
from chat.consumers.messages import NewActiveCallRoom, InBlockIncomingCall
from management.models.matches import Match
from django.views.decorators.csrf import csrf_exempt
import json
from django.http import JsonResponse
import asyncio


@csrf_exempt
def livekit_webhook(request):
    print("Webhook received:", request)
    data = json.loads(request.body)
    print(data)

    event = LivekitWebhookEvent.objects.create(data=data)

    # Events to track: ['participant_joined', 'participant_left']
    if data["event"] == "participant_joined":
        # 1 - we determine the Room
        room_id = data["room"]["name"]
        room = LiveKitRoom.objects.get(uuid=room_id)

        # 2 - we determine the user that just joined
        participant_id = data["participant"]["identity"]
        user = User.objects.get(hash=participant_id)

        # 4 - we determine if a session is already active for that room
        active_session = LivekitSession.objects.filter(room=room, is_active=True)
        if active_session.exists():
            session = active_session.first()
            if user == room.u1:
                session.u1_active = True
                session.u1_was_active = True
                session.both_have_been_active = session.both_have_been_active or session.u2_active
            elif user == room.u2:
                session.u2_active = True
                session.u2_was_active = True
                session.both_have_been_active = session.both_have_been_active or session.u1_active
        else:
            session = LivekitSession.objects.create(
                room=room,
                u1=room.u1,
                u2=room.u2,
                u1_active=(user == room.u1),
                u2_active=(user == room.u2),
                u1_was_active=(user == room.u1),
                u2_was_active=(user == room.u2),
            )
        session.webhook_events.add(event)
        session.save()

        # 5 - send 'NewActiveCall' event to the partner of the user that joined
        partner = room.u1 if user == room.u2 else room.u2
        NewActiveCallRoom(call_room=SerializeLivekitSession(session, context={"user": partner}).data).send(partner.hash)

    if data["event"] == "participant_left":
        # 1 - we determine the Room
        room_id = data["room"]["name"]
        room = LiveKitRoom.objects.get(uuid=room_id)

        # 2 - we determine the user that just joined
        participant_id = data["participant"]["identity"]
        user = User.objects.get(hash=participant_id)

        # 3 - we determine if a session is already active for that room
        active_session = LivekitSession.objects.filter(room=room, is_active=True)
        if active_session.exists():
            session = active_session.first()
            if user == room.u1:
                session.u1_active = False
            elif user == room.u2:
                session.u2_active = False
            if (not session.u1_active) and (not session.u2_active):
                session.is_active = False
                session.end_time = timezone.now()

                # session ended, now we could trigger either
                # 1) a 'CallEnded' event to the partner of the user that left
                # 2) a 'MissedCall' event to the partner of the user that left
                # Both these evenents should have a 'time_threshold' to determine if the call was missed or ended

                if session.both_have_been_active:
                    # 1 - send 'CallEnded' event to the partner of the user that left
                    # TOOD: do we want a minimum time threshold for a call to be considered 'ended/successful'?
                    partner = room.u1 if user == room.u2 else room.u2
                    # update the 'counters' on the Match object
                    match = Match.get_match(room.u1, room.u2).first()
                    match.total_mutal_video_calls_counter += 1
                    match.latest_interaction_at = timezone.now()
                    match.save()
                else:
                    # 2 - send 'MissedCall' event to the partner of the user that left
                    partner = room.u1 if user == room.u2 else room.u2
        session.webhook_events.add(event)
        session.save()

        # 4 - send 'BlockIncomingCall' enent to the parter of the user that left
        partner = room.u1 if user == room.u2 else room.u2
        InBlockIncomingCall(sender_id=participant_id).send(partner.hash)

    return JsonResponse({"status": "ok"})


class AuthenticateRoomParams(serializers.Serializer):
    partner_id = serializers.CharField()


async def create_livekit_room(room_name):
    lkapi = livekit_api.LiveKitAPI(url=settings.LIVEKIT_URL, api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
    results = await lkapi.room.list_rooms(livekit_api.ListRoomsRequest())
    print("Rooms:", results)
    if room_name not in [room.name for room in results.rooms]:
        room_info = await lkapi.room.create_room(
            livekit_api.CreateRoomRequest(name=room_name),
        )
        print("Created room that didn't exist:", room_name, room_info)
    await lkapi.aclose()


@extend_schema(request=AuthenticateRoomParams(many=False), responses={200: {"token": "string"}})
@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def authenticate_live_kit_room(request):
    # 1 - gather the user
    user = request.user
    partner = User.objects.get(hash=request.data["partner_id"])

    chat = ChatSerializer(Chat.get_chat([user, partner]), context={"user": user}).data

    # 2 - the room MUST exist for the user and the partner ( will error if not )
    livekit_room = LiveKitRoom.get_room(user, partner)

    # 3 make sure the livekit room is active
    loop = asyncio.new_event_loop()
    loop.run_until_complete(create_livekit_room(str(livekit_room.uuid)))
    loop.close()

    # 4 - generate autenticaton token
    token = (
        livekit_api.AccessToken(api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
        .with_identity(user.hash)
        .with_name(f"{user.profile.first_name} {user.profile.second_name[:1]}")
        .with_grants(
            livekit_api.VideoGrants(
                room_join=True,
                room=str(livekit_room.uuid),
            )
        )
        .to_jwt()
    )

    return Response({"token": str(token), "server_url": settings.LIVEKIT_URL, "chat": chat})


api_urls = [
    path("api/livekit/authenticate", authenticate_live_kit_room),
    path("api/livekit/webhook", livekit_webhook),
]
