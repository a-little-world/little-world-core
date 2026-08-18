"""Public Match Overview retrieve — participants, matching users, and staff."""

from chat.models import Chat
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from management.analytics.match_journey.snapshots import (
    build_snapshot_for_match,
    qualifying_call_history,
    snapshot_to_dict,
)
from management.authentication import NativeOnlyJWTAuthentication
from management.models.matches import Match
from management.models.profile import CensoredProfileSerializer
from management.models.unconfirmed_matches import MatchType
from management.models.user import User
from management.permissions import ManagementPermission


def _is_matching_operator(user: User) -> bool:
    return bool(user.is_staff or user.has_perm(ManagementPermission.MATCHING_USER))


def _person_payload(user: User) -> dict:
    serialized = CensoredProfileSerializer(user.profile).data
    return {
        "id": str(user.uuid),
        "first_name": serialized["first_name"],
        "image": serialized.get("image"),
        "image_type": serialized.get("image_type"),
        "avatar_config": serialized.get("avatar_config"),
        "user_type": serialized.get("user_type"),
    }


def _pair_chat(match: Match) -> Chat | None:
    """The chat this pair actually talk in, or None.

    Not simply the newest row. ``Chat.is_temporary`` marks in-call random-call chats,
    which are excluded from the chat list, and a pair can hold more than one row —
    ``video/random_calls.py`` looks a pair up as ``(u1, u2)`` only, so a reversed pair
    gets a second chat. Newest-first would then hand the page a chat the recipient
    cannot see in their list, or an empty one while the messages sit on an older row.
    Rare (7 of 21,700 matches hold more than one chat) but the person who hits it lands
    in an empty conversation.

    Preference: has messages, then not temporary, then newest.
    """
    chats = (
        Chat.objects.filter(Q(u1=match.user1, u2=match.user2) | Q(u1=match.user2, u2=match.user1))
        .annotate(message_count=Count("message"))
        .order_by("-created")
    )
    return min(
        chats,
        key=lambda chat: (chat.message_count == 0, chat.is_temporary),
        default=None,
    )


def _call_direction(*, initiator_user_id: int | None, viewer_id: int) -> str:
    """Who started the call, from the viewer's side.

    ``"unknown"`` when the session has no recorded initiator — 2,330 of 15,859 qualifying
    sessions (15%) have a null ``first_active_user``. Defaulting those to ``"outgoing"``
    told every viewer they placed the call, so both participants saw "outgoing" for the
    same call. A missing fact is its own value, not a coin flip (conventions §7).
    """
    if initiator_user_id is None:
        return "unknown"
    return "outgoing" if initiator_user_id == viewer_id else "incoming"


@extend_schema(summary="Match overview snapshot and qualifying call history")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def match_overview(request, match_uuid):
    """Activity snapshot for one match.

    Participants always see their own match. Staff and matching users
    (``ManagementPermission.MATCHING_USER``) may also open a match they are not on;
    the payload is still a participant page, rendered from the volunteer's side.
    Aggregation lives in ``management.analytics.match_journey``; this view only
    authorizes, maps viewer-relative call direction, and returns JSON.
    """
    # No `as_of` from the query string. It exists so the builders are testable
    # (conventions §10); letting a caller pass it would let them shift `current_week`,
    # `is_free_play` and the streaks their own page reports. Tests call
    # `build_snapshot_for_match(match, as_of=...)` directly.
    visible = Match.objects.select_related("user1__profile", "user2__profile").exclude(match_type=MatchType.TEMPORARY)
    if not _is_matching_operator(request.user):
        visible = visible.filter(Q(user1=request.user) | Q(user2=request.user))
    match = get_object_or_404(visible, uuid=match_uuid)

    snapshot = build_snapshot_for_match(match)
    # An operator is not on the match, so the page needs a side to render from — "Du",
    # the partner named in the copy, and incoming/outgoing are all relative to someone.
    # It renders the volunteer's, so an operator sees what the volunteer sees.
    if request.user.pk in (match.user1_id, match.user2_id):
        self_user = request.user
    else:
        self_user = match.get_volunteer()
    partner = match.get_partner(self_user)

    chat = _pair_chat(match)
    calls = [
        {
            "uuid": row["uuid"],
            "started_at": row["started_at"],
            "duration_seconds": row["duration_seconds"],
            "direction": _call_direction(
                initiator_user_id=row["initiator_user_id"],
                viewer_id=self_user.pk,
            ),
        }
        for row in qualifying_call_history(match)
    ]
    return Response(
        {
            "snapshot": snapshot_to_dict(snapshot),
            "calls": calls,
            "chat_id": None if chat is None else str(chat.uuid),
            "partner": _person_payload(partner),
            "self": _person_payload(self_user),
        }
    )
