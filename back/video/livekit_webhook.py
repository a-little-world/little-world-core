import json
from datetime import timedelta

from chat.consumers.messages import InBlockIncomingCall, NewActiveCallRoom
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from management.models.matches import Match
from management.models.user import User

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
    # Handels webhook events for video calls and random calls
    # The room is marked with 'room.random_call_room = True' if it is a random call
    # Then we also:
    # 1. Mark the session as 'random_call_session'
    # 2. TODO: Several Events shoudn't be tracked for random calls!
    if data["event"] == "participant_joined":
        # 1 - we determine the Room
        room_id = data["room"]["name"]
        room = LiveKitRoom.objects.get(uuid=room_id)
        if room.random_call_room:
            random_call_session = True

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
                random_call_session=random_call_session,
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
                    except Exception:
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
                    except Exception:
                        print("Cound't send call widged to first_active_user")
                        pass

            # check if the call review pop-up should be triggered
            call_duration = end_time - session.created_at
            if session.both_have_been_active and call_duration >= timedelta(minutes=5):
                try:
                    # Now we can trigger the call review pop-up for the user that left
                    from chat.consumers.messages import PostCallSurvey

                    PostCallSurvey(post_call_survey={"live_session_id": str(session.uuid)}).send(user.hash)
                except Exception:
                    print("Cound't tigger the post call survey")
                    pass

        session.webhook_events.add(event)
        session.save()

        # 4 - send 'BlockIncomingCall' event to the partner of the user that left
        partner = room.u1 if user == room.u2 else room.u2
        InBlockIncomingCall(sender_id=participant_id).send(partner.hash)

    return JsonResponse({"status": "ok"})


api_urls = [path("api/livekit/webhook", livekit_webhook)]
