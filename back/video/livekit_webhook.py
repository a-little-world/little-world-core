import json
import logging

from chat.consumers.messages import InBlockIncomingCall, NewActiveCallRoom
from chat.models import Chat, ChatConnections
from django.db.models import F, Q
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from management.models.matches import Match
from management.models.user import PushNotificationType, User
from management.surveys import offer_post_call_survey
from management.tasks import push_notification_background
from translations import get_translation

from video.models import (
    LiveKitRoom,
    LivekitSession,
    LivekitWebhookEvent,
    RandomCallMatching,
    SerializeLivekitSession,
)

logger = logging.getLogger(__name__)


def _mark_session_participant_active(session, room, user):
    if user == room.u1:
        session.u1_active = True
        session.u1_was_active = True
        session.both_have_been_active = session.both_have_been_active or session.u2_active
    elif user == room.u2:
        session.u2_active = True
        session.u2_was_active = True
        session.both_have_been_active = session.both_have_been_active or session.u1_active


def _bump_match_mutual_video_call_counter(room):
    """Count a mutual video call as soon as both participants have joined."""
    match = Match.get_match(room.u1, room.u2).first()
    if match is None:
        return
    match.total_mutal_video_calls_counter += 1
    match.latest_interaction_at = timezone.now()
    match.save(update_fields=["total_mutal_video_calls_counter", "latest_interaction_at", "updated_at"])


def process_webhook_random_call__participant_joined(data, event, participant_id, user, room_id, room):
    # 4 - we determine if a session is already active for that room
    active_session = LivekitSession.objects.filter(room=room, is_active=True)
    session = None
    if active_session.exists():
        session = active_session.first()
        _mark_session_participant_active(session, room, user)
    else:
        # TODO: Here we additionally want to create a 'RandomCallSession' DB Object!
        session = LivekitSession.objects.create(
            room=room,
            u1=room.u1,
            u2=room.u2,
            u1_active=(user == room.u1),
            u2_active=(user == room.u2),
            u1_was_active=(user == room.u1),
            u2_was_active=(user == room.u2),
            first_active_user=user,
            random_call_session=True,
        )
    if session is not None:
        session.webhook_events.add(event)
        session.save()
    else:
        raise Exception(
            "Edge-Case Detected (@tbscode) random call participant joined: session not found for room:", room.uuid
        )


def _notify_incoming_call(caller, partner, session):
    partner_was_active = session.u1_was_active if partner == session.u1 else session.u2_was_active
    if partner_was_active or ChatConnections.is_user_online(partner):
        return
    chat = Chat.get_chat([caller, partner])
    title = get_translation("push_notification.incoming_call.title", partner.profile.display_language)
    description = get_translation(
        "push_notification.incoming_call.description", partner.profile.display_language
    ).format(name=caller.first_name)

    push_notification_background.delay(
        partner.pk,
        title=title,
        description=description,
        notification_type=PushNotificationType.CHAT,
        path=f"/app/chat/{str(chat.uuid)}" if chat is not None else "/app/chat/",
        group=f"call:{str(session.uuid)}",
    )


def process_webhook_classic_call__participant_joined(data, event, participant_id, user, room_id, room):
    # 4 - we determine if a session is already active for that room
    active_session = LivekitSession.objects.filter(room=room, is_active=True)
    session = None
    already_mutual = False
    if active_session.exists():
        session = active_session.first()
        already_mutual = session.both_have_been_active
        _mark_session_participant_active(session, room, user)
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
            random_call_session=False,
        )

    if session is not None:
        session.webhook_events.add(event)
        session.save()
        if session.both_have_been_active and not already_mutual:
            _bump_match_mutual_video_call_counter(room)
        # 5 - send 'NewActiveCall' event to the partner of the user that joined
        partner = room.u1 if user == room.u2 else room.u2
        NewActiveCallRoom(call_room=SerializeLivekitSession(session, context={"user": partner}).data).send(
            str(partner.uuid)
        )
        try:
            _notify_incoming_call(user, partner, session)
        except Exception:
            pass
    else:
        raise Exception(
            "Edge-Case Detected (@tbscode) classic call participant joined: session not found for room:", room.uuid
        )


def process_webhook_classic_call__participant_left(data, event, participant_id, user, room_id, room):
    # 3 - we determine if a session is already active for that room
    active_session = LivekitSession.objects.filter(room=room, is_active=True)
    session = None
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
                # Mutual video call counter is bumped when both become active (on join), not on leave.
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

                # Offer the post-call survey to *both* participants. Creating the rows is
                # the whole job — each client's next poll of /api/surveys/pending finds
                # them, so the survey does not depend on anyone holding an open WebSocket.
                #
                # Deliberately here rather than per `participant_left` event. `end_time` is
                # assigned in this branch, and `offer_post_call_survey` returns early while
                # it is still None — so the first person to leave was silently skipped and
                # only the last one was ever asked. No error, no row, half the answers.
                for participant in (session.u1, session.u2):
                    try:
                        offer_post_call_survey(participant, session)
                    except Exception:
                        logger.exception(
                            "Could not offer the post call survey to user %s for session %s",
                            participant.pk,
                            session.uuid,
                        )

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

    if session is not None:
        session.webhook_events.add(event)
        session.save()
    else:
        raise Exception(
            "Edge-Case Detected (@tbscode) classic call participant left: session not found for room:", room.uuid
        )

    # 4 - send 'BlockIncomingCall' event to the partner of the user that left
    partner = room.u1 if user == room.u2 else room.u2
    InBlockIncomingCall(sender_id=participant_id).send(str(partner.uuid))


def _matching_for_completed_random_call(user, partner, *, session_created_at):
    """Resolve the single accepted, in-progress matching for this call."""
    matching_qs = RandomCallMatching.objects.filter(
        Q(u1=user, u2=partner) | Q(u1=partner, u2=user),
        accepted=True,
        completed=False,
    )
    if session_created_at is not None:
        matching_qs = matching_qs.filter(lobby__start_time__lte=session_created_at).filter(
            Q(lobby__end_time__gte=session_created_at) | Q(lobby__end_time__isnull=True)
        )
    return matching_qs.order_by(F("accepted_at").desc(nulls_last=True), "-pk").first()


def process_webhook_random_call__participant_left(data, event, participant_id, user, room_id, room):
    # 3 - we determine if a session is already active for that room
    active_session = LivekitSession.objects.filter(room=room, is_active=True)
    session = None
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
                partner = room.u1 if user == room.u2 else room.u2
                matching = _matching_for_completed_random_call(
                    user,
                    partner,
                    session_created_at=session.created_at,
                )
                if matching is not None:
                    RandomCallMatching.objects.filter(pk=matching.pk).update(
                        completed=True,
                        in_session=False,
                        completed_at=end_time,
                        ended_by=user,
                    )
                else:
                    logger.warning(
                        "Random call LiveKit session ended but no accepted matching found "
                        "(room=%s user=%s partner=%s session_created_at=%s)",
                        room.uuid,
                        user.uuid,
                        partner.uuid,
                        session.created_at,
                    )

            else:
                # 2 - send 'MissedCall' event to the partner of the user that left
                # check which user endered the call first
                partner = room.u1 if user == room.u2 else room.u2

    if session is not None:
        session.webhook_events.add(event)
        session.save()
    else:
        raise Exception(
            "Edge-Case Detected (@tbscode) random call participant left: session not found for room:", room.uuid
        )

    # 4 - send 'BlockIncomingCall' event to the partner of the user that left
    partner = room.u1 if user == room.u2 else room.u2
    InBlockIncomingCall(sender_id=participant_id).send(str(partner.uuid))


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
    random_call_session = False
    if data["event"] == "participant_joined":
        # 1 - we determine the Room
        room_id = data["room"]["name"]
        room = LiveKitRoom.objects.get(uuid=room_id)
        if room.random_call_room:
            random_call_session = True

        # 2 - we determine the user that just joined
        participant_id = data["participant"]["identity"]
        user = User.objects.get(uuid=participant_id)

        if room.random_call_room:
            process_webhook_random_call__participant_joined(data, event, participant_id, user, room_id, room)
        else:
            process_webhook_classic_call__participant_joined(data, event, participant_id, user, room_id, room)

    if data["event"] == "participant_left":
        # 1 - we determine the Room
        room_id = data["room"]["name"]
        room = LiveKitRoom.objects.get(uuid=room_id)

        if room.random_call_room:
            random_call_session = True

        # 2 - we determine the user that just joined
        participant_id = data["participant"]["identity"]
        user = User.objects.get(uuid=participant_id)

        if random_call_session:
            process_webhook_random_call__participant_left(data, event, participant_id, user, room_id, room)
        else:
            process_webhook_classic_call__participant_left(data, event, participant_id, user, room_id, room)

    return JsonResponse({"status": "ok"})


api_urls = [path("api/livekit/webhook", livekit_webhook)]
