from typing import Enum 
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from typing import Literal
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from dataclasses import dataclass
from django.utils.translation import pgettext_lazy
from rest_framework import serializers
from management.controller import match_users
from management.models.settings import UnsubscibeOptions, EmailSettings

@dataclass
class UnsubscribeParams:
    unsubscribe_type: UnsubscibeOptions
    choice: bool = False

@dataclass
class UnsubscribeLinkParams:
    settings_hash: str
    unsubscribe_type: UnsubscibeOptions
    choice: bool = False
    
class UnsubscribeParamsSerializer(DataclassSerializer):
    class Meta:
        dataclass = UnsubscribeParams

class UnsubscribeParamsLinkSerializer(DataclassSerializer):
    class Meta:
        dataclass = UnsubscribeLinkParams

def update_email_settings(data, email_settings):
    if data.choice and (data.unsubscribe_type in email_settings):
        email_settings.remove(data.unsubscribe_type)
        email_settings.save()
        return Response(pgettext_lazy("unsubscribe_email.success", "You have been unsubscribed from this email type"))

    elif not data.choice and (data.unsubscribe_type not in email_settings):
        email_settings.add(data.unsubscribe_type)
        email_settings.save()
        return Response(pgettext_lazy("unsubscribe_email.success", "You have been subscribed to this email type"))
    
    return Response(pgettext_lazy("unsubscribe_email.success", "No email settings where changed"))
    
@extend_schema(
    request=UnsubscribeParamsSerializer(many=False),
)
@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def unsubscribe_email(request):
    
    serializer = UnsubscribeParamsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    data = serializer.save()
    
    email_settings = request.user.settings.email_settings
    
    return update_email_settings(data, email_settings)
    

@extend_schema(
    request=UnsubscribeParamsLinkSerializer(many=False),
)
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def unsubscribe_link(request):
    """
    A unsubscribe link that can be acessed by email settings hash rather than being signed in 
    TODO: do this need aditional security? can anyone brute force uuids?
    """
    serializer = UnsubscribeParamsLinkSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    data = serializer.save()
    
    email_settings = EmailSettings.objects.filter(hash=data.settings_hash)
    
    return update_email_settings(data, email_settings)
    
    