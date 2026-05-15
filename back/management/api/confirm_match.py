"""
This contains all api's related to confirming or denying a match
"""

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from translations import get_translation

from management.api.matches import AdvancedUserMatchSerializer
from management.authentication import NativeOnlyJWTAuthentication
from management.controller import match_users
from management.models.state import State
from management.models.unconfirmed_matches import ProposedMatch


class ConfirmMatchSerializer(serializers.Serializer):
    unconfirmed_match_uuid = serializers.CharField(required=False, allow_blank=False)
    # Backward-compatible fallback during the hash -> uuid transition.
    unconfirmed_match_hash = serializers.CharField(required=False, allow_blank=False)
    confirm = serializers.BooleanField()
    deny_reason = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("unconfirmed_match_uuid") and not attrs.get("unconfirmed_match_hash"):
            raise serializers.ValidationError(
                {"unconfirmed_match_uuid": get_translation("confirm_match.unconfimed_match_not_found")}
            )
        return attrs


@extend_schema(
    request=ConfirmMatchSerializer(many=False),
)
@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def confirm_match(request):
    # Could be renamed to accept_reject_match or similar
    serializer = ConfirmMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.validated_data

    match_identifier = data.get("unconfirmed_match_uuid") or data.get("unconfirmed_match_hash")
    unconfirmed_match = ProposedMatch.objects.filter(hash=match_identifier, closed=False)

    # First check if that unconfirmed match exists
    if not unconfirmed_match.exists():
        raise serializers.ValidationError(get_translation("confirm_match.unconfimed_match_not_found"))

    unconfirmed_match = unconfirmed_match.first()
    assert unconfirmed_match

    # then check if maybe this match is already expired
    if unconfirmed_match.is_expired(close_if_expired=True, send_mail_if_expired=True):
        # auto close if expired, do send mail if not send

        raise serializers.ValidationError(get_translation("confirm_match.unconfimed_match_expired"))

    # now check the user choice
    if data["confirm"]:
        matching = match_users(
            {unconfirmed_match.user1, unconfirmed_match.user2},
            match_type=unconfirmed_match.match_type,
        )
        unconfirmed_match.closed = True
        unconfirmed_match.save()

        partner = unconfirmed_match.get_partner(request.user)

        msg = get_translation("confirm_match.match_confirmed")

        # Now we need to update the partner that was just accepted via callback
        matches = AdvancedUserMatchSerializer([matching], many=True, context={"user": partner}).data

        from chat.consumers.messages import InUnconfirmedMatchAdded

        InUnconfirmedMatchAdded(matches[0]).send(str(partner.uuid))

        return Response(
            {
                "message": msg,
                "match": AdvancedUserMatchSerializer(matching, many=False, context={"user": request.user}).data,
            }
        )
    else:
        # just close the unconfirmed match
        unconfirmed_match.closed = True
        unconfirmed_match.rejected = True
        unconfirmed_match.rejected_at = timezone.now()
        unconfirmed_match.rejected_by = request.user
        unconfirmed_match.rejected_reason = data.get("deny_reason")
        unconfirmed_match.save()

        if not request.user.state.has_match_priority:
            request.user.state.searching_state = State.SearchingStateChoices.IDLE

        request.user.state.save()

        return Response(get_translation("confirm_match.match_rejected"))
