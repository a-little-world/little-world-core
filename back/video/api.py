import asyncio
import json
import uuid
from datetime import timedelta

from django.db.models import Q
from rest_framework_simplejwt.authentication import JWTAuthentication
from chat.consumers.messages import InBlockIncomingCall, NewActiveCallRoom, OutgoingCallRejected
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
)


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
                first_active_user=user,
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
            end_time = timezone.now()
            if (not session.u1_active) and (not session.u2_active):
                session.is_active = False
                session.end_time = end_time

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
                    call_duration = session.end_time - session.created_at

                    try:
                        # send chat message from: session.first_active_user -> widget_recipient
                        def duration_to_text(duration):
                            seconds = int(duration.total_seconds())
                            minutes, seconds = divmod(seconds, 60)

                            if minutes > 0:
                                return f"{minutes} minute{'s' if minutes > 1 else ''}"
                            else:
                                return f"{seconds} second{'s' if seconds > 1 else ''}"

                        widget_recipient = room.u1 if session.first_active_user == room.u2 else room.u2
                        # chat = Chat.get_chat([session.first_active_user, widget_recipient])
                        # e.g.: <CallWidget {"header": "Call completed", "description": "10 minutes", "isMissed": false}>
                        # usr.message('<CallWidget {"description": "10 minutes"}></CallWidget>', sender=usr2, auto_mark_read=True, parsable_message=True)
                        widget_recipient.message(
                            '<CallWidget {"description": "' + duration_to_text(call_duration) + '"}></CallWidget>',
                            sender=session.first_active_user,
                            auto_mark_read=True,
                            parsable_message=True,
                            send_message_incoming=True,
                            send_message_incoming_to_sender=True,
                        )
                    except:
                        print("Cound't send call widged to first_active_user")
                        pass

                else:
                    # 2 - send 'MissedCall' event to the partner of the user that left
                    # check which user endered the call first
                    partner = room.u1 if user == room.u2 else room.u2
                    try:
                        # send chat message from: session.first_active_user -> widget_recipient
                        # chat = Chat.get_chat([session.first_active_user, widget_recipient])
                        # usr.message('<MissedCallWidget {"description": "Click to return call", "isMissed": true}></MissedCallWidget>', sender=usr2, auto_mark_read=True, parsable_message=True)
                        widget_recipient = room.u1 if session.first_active_user == room.u2 else room.u2
                        widget_recipient.message(
                            "<MissedCallWidget></MissedCallWidget>",
                            sender=session.first_active_user,
                            auto_mark_read=False,
                            parsable_message=True,
                            send_message_incoming=True,
                            send_message_incoming_to_sender=True,
                        )
                    except:
                        print("Cound't send call widged to first_active_user")
                        pass

            # check if the call review pop-up should be triggered
            call_duration = end_time - session.created_at
            if session.both_have_been_active and call_duration >= timedelta(minutes=5):
                try:
                    # Now we can trigger the call review pop-up for the user that left
                    from chat.consumers.messages import PostCallSurvey

                    PostCallSurvey(post_call_survey={"live_session_id": str(session.uuid)}).send(user.hash)
                except:
                    print("Cound't tigger the post call survey")
                    pass

        session.webhook_events.add(event)
        session.save()

        # 4 - send 'BlockIncomingCall' event to the partner of the user that left
        partner = room.u1 if user == room.u2 else room.u2
        InBlockIncomingCall(sender_id=participant_id).send(partner.hash)

    return JsonResponse({"status": "ok"})


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

    return Response({
        "token": str(token), 
        "server_url": settings.LIVEKIT_URL, 
        "chat": chat
    })


class PostCallReviewParams(serializers.Serializer):
    live_session_id = serializers.UUIDField(required=False, allow_null=True)
    rating = serializers.IntegerField(required=True)
    review = serializers.CharField(required=False, allow_blank=True)
    review_id = serializers.IntegerField(required=False, allow_null=True)

    def to_internal_value(self, data):
        if "live_session_id" in data:
            try:
                # If a non parsable uuid is sent, we set it to None
                uuid.UUID(str(data["live_session_id"]))
            except (ValueError, TypeError, AttributeError):
                data["live_session_id"] = None

        return super().to_internal_value(data)


@extend_schema(request=PostCallReviewParams(many=False), responses={200: {"status": "ok"}})
@api_view(["POST"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([IsAuthenticated])
def post_call_review(request):
    serializer = PostCallReviewParams(data=request.data)
    if not serializer.is_valid():
        return Response({"status": "error", "message": "Invalid Review Data"}, status=400)
    validated_data = serializer.validated_data
    live_session = None
    if validated_data.get("live_session_id"):
        live_session = LivekitSession.objects.filter(uuid=validated_data["live_session_id"])
        if live_session.exists():
            live_session = live_session.first()
        else:
            live_session = None  # No error let the user still submit his review
    review_text = validated_data.get("review", "")
    rating = validated_data["rating"]
    review_id = validated_data.get("review_id", None)
    if not (review_id is None):
        # then we just update the existing review
        review = PostCallReview.objects.get(id=review_id)
        review.rating = rating
        review.review = review_text
        review.save()
    else:
        review = PostCallReview.objects.create(
            user=request.user, live_session=live_session, review=review_text, rating=rating
        )

    # Can be triggered anytime via ( you may obmit the live_session_id if you want to )
    # from chat.consumers.messages import PostCallSurvey
    # PostCallSurvey(post_call_survey={"live_session_id": str(live_session.uuid)}).send(request.user.hash)

    return Response({"status": "ok", "review_id": review.id})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, JWTAuthentication])
def active_call_rooms(request):
    """
    Returns active call rooms for the authenticated user.
    """
    user = request.user
    
    try:
        # find all active calls
        all_active_rooms = LivekitSession.objects.filter(
            Q(room__u1=user, is_active=True, u2_active=True, u1_active=False)
            | Q(room__u2=user, is_active=True, u1_active=True, u2_active=False)
        )
        
        return Response(SerializeLivekitSession(all_active_rooms, context={"user": user}, many=True).data)
    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def call_retrigger(request):
    try:
        partner = User.objects.get(hash=request.data["partner_id"])
        room = LiveKitRoom.objects.get(uuid=request.data["session_id"])
        active_session = LivekitSession.objects.filter(room=room, is_active=True)
       
        if active_session.exists():
            session = active_session.first()
            NewActiveCallRoom(call_room=SerializeLivekitSession(session, context={"user": partner}).data).send(partner.hash)
            return Response({"status": "ok"})
        return Response({"error": "Session not found"}, status=400)
    except Exception as e:
        return Response({"error": str(e)}, status=400)
    

class CallRejectedParams(serializers.Serializer):
    partner_id = serializers.CharField(required=True)
    session_id = serializers.CharField(required=True)


@extend_schema(request=CallRejectedParams(many=False), responses={200: {"status": "ok"}})
@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def call_rejected(request):
    """
    Handles call rejection and sends OutgoingCallRejected message to the call initiator.
    """
    serializer = CallRejectedParams(data=request.data)
    if not serializer.is_valid():
        return Response({"status": "error", "message": "Invalid parameters"}, status=400)
    
    validated_data = serializer.validated_data
    
    try:
        # Get the partner who initiated the call
        partner = User.objects.get(hash=validated_data["partner_id"])
        
        # Get the room/session
        room = LiveKitRoom.objects.get(uuid=validated_data["session_id"])
        
        # Verify the room involves the authenticated user
        if room.u1 != request.user and room.u2 != request.user:
            return Response({"status": "error", "message": "Unauthorized access to this call"}, status=403)
        
        # Verify the partner is the other participant in the room
        if room.u1 != partner and room.u2 != partner:
            return Response({"status": "error", "message": "Invalid partner for this call"}, status=400)

        # Send OutgoingCallRejected message to the partner (call initiator)
        OutgoingCallRejected().send(partner.hash)
        return Response({"status": "ok"})
        
    except User.DoesNotExist:
        return Response({"status": "error", "message": "Partner not found"}, status=404)
    except LiveKitRoom.DoesNotExist:
        return Response({"status": "error", "message": "Call session not found"}, status=404)
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=400)


api_urls = [
    path("api/livekit/review", post_call_review),
    path("api/call_rooms", active_call_rooms, name="active_call_rooms_api"),
    path("api/call_rejected", call_rejected),
    path("api/call_retrigger", call_retrigger),
    path("api/livekit/authenticate", authenticate_live_kit_room),
    path("api/livekit/webhook", livekit_webhook),
]
