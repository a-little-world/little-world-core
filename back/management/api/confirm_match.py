"""
This contains all api's related to confirming or denying a match
"""

from drf_spectacular.utils import extend_schema
from management.api.user_data import AdvancedUserMatchSerializer
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from dataclasses import dataclass
from management.models.unconfirmed_matches import ProposedMatch
from rest_framework import serializers
from management.controller import match_users
from translations import get_translation


@dataclass
class ConfirmMatchData:
    unconfirmed_match_hash: str
    confirm: bool


class ConfirmMatchSerializer(DataclassSerializer):
    class Meta:
        dataclass = ConfirmMatchData


@extend_schema(
    request=ConfirmMatchSerializer(many=False),
)
@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def confrim_match(request):
    # TODO Inconsisten naming this ist the accept / deny api
    serializer = ConfirmMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.save()

    unconfirmed_match = ProposedMatch.objects.filter(hash=data.unconfirmed_match_hash, closed=False)

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
    if data.confirm:
        matching = match_users({unconfirmed_match.user1, unconfirmed_match.user2})
        unconfirmed_match.closed = True
        unconfirmed_match.save()

        partner = unconfirmed_match.get_partner(request.user)

        msg = get_translation("confirm_match.match_confirmed")

        # Now we need to update the partner that was just accepted via callback
        matches = AdvancedUserMatchSerializer([matching], many=True, context={"user": partner}).data

        from chat.consumers.messages import InUnconfirmedMatchAdded

        InUnconfirmedMatchAdded(matches[0]).send(partner.hash)

        return Response({"message": msg, "match": AdvancedUserMatchSerializer(matching, many=False, context={"user": request.user}).data })
    else:
        # just close the unconfirmed match
        unconfirmed_match.closed = True
        unconfirmed_match.save()

        return Response(get_translation("confirm_match.match_rejected"))
