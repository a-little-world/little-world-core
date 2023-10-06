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
from django.utils.translation import pgettext_lazy
from rest_framework import serializers



@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def callcom_websocket_callback(request):
    """
    Received callcom event callbacks, this should simply send a message in the admin chat if an appointment was booked.
    """
    
    print("callback received")
    print(request.data)

    
    return Response("ok")