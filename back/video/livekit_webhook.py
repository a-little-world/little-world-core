import json
import logging

from chat.consumers.messages import InBlockIncomingCall, NewActiveCallRoom
from chat.models import Chat, ChatConnections
from django.db import IntegrityError, transaction
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


_ACTIVE_SESSION_PARTICIPANT_FIELDS = (
    "u1_active",
    "u2_active",
    "u1_was_active",
    "u2_was_active",
    "both_have_been_active",
)


def _lock_room(room):
    LiveKitRoom.objects.select_for_update().get(pk=room.pk)


def _active_sessions(room):
    return LivekitSession.objects.filter(room=room, is_active=True).order_by("created_at", "pk")


def _create_join_session(room, user, *, random_call_session):
    return LivekitSession.objects.create(
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


def _attach_participant_and_save(session, room, user):
    _mark_session_participant_active(session, room, user)
    session.save(update_fields=_ACTIVE_SESSION_PARTICIPANT_FIELDS)


def _get_or_create_active_session(room, user, *, random_call_session):
    """One active session per room, even when both participants join at once.

    LiveKit can deliver the two `participant_joined` webhooks to different workers.
    Without locking, both see no active session and each creates a one-sided row, so a
    successful call is stored twice with `both_have_been_active=False`.
    """
    with transaction.atomic():
        _lock_room(room)
        session = _active_sessions(room).first()
        already_mutual = bool(session and session.both_have_been_active)
        if session is None:
            try:
                with transaction.atomic():
                    session = _create_join_session(room, user, random_call_session=random_call_session)
            except IntegrityError:
                session = _active_sessions(room).first()
                if session is None:
                    raise
                already_mutual = session.both_have_been_active
                _attach_participant_and_save(session, room, user)
        else:
            _attach_participant_and_save(session, room, user)
        return session, already_mutual


def _bump_match_mutual_video_call_counter(room):
    """Count a mutual video call as soon as both participants have joined."""
    match = Match.get_match(room.u1, room.u2).first()
    if match is None:
        return
    match.total_mutal_video_calls_counter += 1
    match.latest_interaction_at = timezone.now()
    match.save(update_fields=["total_mutal_video_calls_counter", "latest_interaction_at", "updated_at"])


def process_webhook_random_call__participant_joined(data, event, participant_id, user, room_id, room):
    session, _ = _get_or_create_active_session(room, user, random_call_session=True)
    session.webhook_events.add(event)


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
    session, already_mutual = _get_or_create_active_session(room, user, random_call_session=False)
    session.webhook_events.add(event)
    if session.both_have_been_active and not already_mutual:
        _bump_match_mutual_video_call_counter(room)
    partner = room.u1 if user == room.u2 else room.u2
    NewActiveCallRoom(call_room=SerializeLivekitSession(session, context={"user": partner}).data).send(
        str(partner.uuid)
    )
    try:
        _notify_incoming_call(user, partner, session)
    except Exception:
        pass


def _mark_participant_left(room, user):
    """Clear this participant's in-room flag. Close the session if both are gone.

    Same room lock as join: two near-simultaneous leaves otherwise each read both-still-in
    and the last save can restore one flag, leaving the call stuck open.
    """
    with transaction.atomic():
        _lock_room(room)
        session = _active_sessions(room).first()
        if session is None:
            return None, False
        if user == room.u1:
            session.u1_active = False
        elif user == room.u2:
            session.u2_active = False
        call_ended = (not session.u1_active) and (not session.u2_active)
        if call_ended:
            session.is_active = False
            # A delayed leave on a session the cap job already stamped must not replace
            # that end with "now" (the multi-day overwrite).
            if session.unusual_length:
                session.save(update_fields=["u1_active", "u2_active", "is_active"])
            else:
                session.end_time = timezone.now()
                session.save(update_fields=["u1_active", "u2_active", "is_active", "end_time"])
        else:
            session.save(update_fields=["u1_active", "u2_active"])
        return session, call_ended


def process_webhook_classic_call__participant_left(data, event, participant_id, user, room_id, room):
    session, call_ended = _mark_participant_left(room, user)
    if session is None:
        # Already closed (both left, or the stuck-session job deactivated the row).
        return
    session.webhook_events.add(event)

    if call_ended:
        if session.both_have_been_active:
            call_duration = session.end_time - session.created_at

            try:

                def duration_to_text(duration):
                    seconds = int(duration.total_seconds())
                    minutes, seconds = divmod(seconds, 60)

                    if minutes > 0:
                        return f"{minutes} minute{'s' if minutes > 1 else ''}"
                    else:
                        return f"{seconds} second{'s' if seconds > 1 else ''}"

                widget_recipient = room.u1 if session.first_active_user == room.u2 else room.u2
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
            try:
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
    session, call_ended = _mark_participant_left(room, user)
    if session is None:
        return
    session.webhook_events.add(event)

    if call_ended and session.both_have_been_active:
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
                completed_at=session.end_time,
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
