"""
This contains all api's related to confirming or denying a match
"""
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from management.models.consumer_connections import ConsumerConnections
from back.utils import CoolerJson
import json
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from django.utils.translation import get_language
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from dataclasses import dataclass
from management.models.unconfirmed_matches import UnconfirmedMatch
from django.utils.translation import pgettext_lazy
from rest_framework import serializers
from management.controller import match_users


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
@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def confrim_match(request):
    # TODO Inconsisten naming this ist the accept / deny api
    serializer = ConfirmMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.save()

    unconfirmed_match = UnconfirmedMatch.objects.filter(
        hash=data.unconfirmed_match_hash, closed=False)

    # First check if that unconfimed match exists
    if not unconfirmed_match.exists():
        raise serializers.ValidationError(
            pgettext_lazy("confirm_match.unconfimed_match_not_found", "This unconfirmed match does not exist, or is already closed"))

    unconfirmed_match = unconfirmed_match.first()
    assert unconfirmed_match

    # then check if maybe this match is already expired
    if unconfirmed_match.is_expired(close_if_expired=True, send_mail_if_expired=True):
        # auto close if expired, do send mail if not send

        raise serializers.ValidationError(
            pgettext_lazy("confirm_match.unconfimed_match_expired", "This unconfirmed match is expired"))

    # now check the user choice
    if data.confirm:
        matching = match_users({unconfirmed_match.user1, unconfirmed_match.user2})
        unconfirmed_match.closed = True
        unconfirmed_match.save()
        
        partner = unconfirmed_match.get_partner(request.user)
        
        msg = pgettext_lazy("confirm_match.match_confirmed", "The match has been confirmed, your match has been made!")

        from management.api.user_data import serialize_matches
        
        # Now we need to update the partner that was just accepted via callback

        matches = serialize_matches([matching], partner)
        payload = {
            "action": "addMatch", 
            "payload": {
                "category": "unconfirmed",
                "match": json.loads(json.dumps(matches[0], cls=CoolerJson))
            }
        }
        ConsumerConnections.notify_connections(partner, event="reduction", payload=payload)


        return Response({
            "message": msg,
            "match": matching.get_serialized(request.user),
            "unconfirmed_matches": [partner.hash]
        })
    else:
        # just close the unconfirmed match
        unconfirmed_match.closed = True
        unconfirmed_match.save()

        # TODO: send a to the user that tha match has been expired
        
        return Response(pgettext_lazy("confirm_match.match_rejected", "The match has been rejected."))
