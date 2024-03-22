from google.cloud import translate_v2
from google.oauth2 import service_account
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework_dataclasses.serializers import DataclassSerializer
from rest_framework import serializers
from drf_spectacular.utils import extend_schema
from django.conf import settings
import json
import base64

class TranslateTextData:
    target: str
    text: str

class TranslateTextSerializer(serializers.Serializer):
    target = serializers.CharField(required=True)
    text = serializers.CharField(required=True)
    

@extend_schema(
    methods=["POST"],
    request=TranslateTextSerializer(many=False)
)
@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def translate(request):
    """
    Translate a text to a given language
    """
    serializer = TranslateTextSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    target = serializer.data['target']
    text = serializer.data['text']
    
    credentials = service_account.Credentials.from_service_account_info(
        settings.GOOGLE_CLOUD_CREDENTIALS
    )

    translate_client = translate_v2.Client(credentials=credentials)

    if isinstance(text, bytes):
        text = text.decode("utf-8")

    result = translate_client.translate(text, target_language=target)

    return result