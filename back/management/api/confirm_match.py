"""
This contains all api's related to confirming or denying a match
"""
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from typing import Literal
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.views.i18n import JavaScriptCatalog, JSONCatalog
from django.utils.translation.trans_real import DjangoTranslation
from django.utils.translation import get_language
from django.conf import settings
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from dataclasses import dataclass
from management.models.no_login_form import NoLoginForm, FORMS
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
    if unconfirmed_match.is_expired(close_if_expired=True):

        raise serializers.ValidationError(
            pgettext_lazy("confirm_match.unconfimed_match_expired", "This unconfirmed match is expired"))

    # now check the user choice
    if data.confirm:
        # TODO: create the actuall matching
        match_users({unconfirmed_match.user1, unconfirmed_match.user2})
        pass
        return Response(pgettext_lazy("confirm_match.match_confirmed", "The match has been confirmed, your match has been made!"))
    else:
        # just close the unconfirmed match
        unconfirmed_match.closed = True
        unconfirmed_match.save()

        # TODO: send a to the user that tha match has been expired
