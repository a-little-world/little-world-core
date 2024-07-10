from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from typing import Literal, get_type_hints
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from dataclasses import dataclass, fields, field
from rest_framework import serializers
from management.controller import match_users,get_translation
from management.models.settings import UnsubscibeOptions, EmailSettings

@dataclass
class UnsubscribeParams:
    unsubscribe_type: UnsubscibeOptions = field(
        default=UnsubscibeOptions.interview_requests,
        metadata={
            "choices": [opt.value for opt in UnsubscibeOptions],
        }
    )
    choice: bool = False

@dataclass
class UnsubscribeLinkParams:
    settings_hash: str
    unsubscribe_type: UnsubscibeOptions = field(
        default=UnsubscibeOptions.interview_requests,
        metadata={
            "choices": [opt.value for opt in UnsubscibeOptions],
        }
    )
    choice: bool = False
    
class UnsubscribeParamsSerializer(DataclassSerializer):
    class Meta:
        dataclass = UnsubscribeParams

class UnsubscribeParamsLinkSerializer(DataclassSerializer):
    class Meta:
        dataclass = UnsubscribeLinkParams

def update_email_settings(data, email_settings, request=None):
    from management.views.main_frontend import info_card

    if (not data.choice) and (not (data.unsubscribe_type in email_settings.unsubscibed_options)):
        email_settings.unsubscibed_options.append(data.unsubscribe_type)
        email_settings.save()
        
        response_text = get_translation("info_view.email_unsubscribed")

        if request:
            return info_card(request,
                             title=get_translation("info_view.email_unsubscribed.title"), 
                             content=response_text,
                             linkText=get_translation("info_view.back_to_home"),
                             )
        else:
            return Response(response_text)

    elif data.choice and (data.unsubscribe_type in email_settings.unsubscibed_options):
        email_settings.unsubscibed_options.remove(data.unsubscribe_type)
        email_settings.save()

        response_text = get_translation("info_view.email_subscribed")
        
        if request:
            return info_card(request,
                             title=get_translation("info_view.email_subscribed.title"), 
                             content=response_text,
                             linkText=get_translation("info_view.back_to_home"),
                             )
        else:
            return Response(response_text)
        
    response_text = get_translation("info_view.email_already_subscribed")
    
    if request:
        return info_card(request,
                         title=get_translation("info_view.email_already_subscribed.title"), 
                         content=response_text,
                         linkText=get_translation("info_view.back_to_home"),
                         )
    else:
        return Response(response_text)
    
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
    parameters=[
        OpenApiParameter(
            name="choice", 
            type=bool, 
            location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            name="unsubscribe_type",
            type=str, 
            enum=UnsubscibeOptions,
            location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            name="settings_hash",
            type=str,
            location=OpenApiParameter.QUERY
        )
    ]
)
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def unsubscribe_link(request):
    """
    A unsubscribe link that can be acessed by email settings hash rather than being signed in 
    TODO: do this need aditional security? can anyone brute force uuids?
    localhost:8000/api/emails/toggle_sub/?choice=False&unsubscribe_type=interview_requests&settings_hash=b489fcb7-ca4c-436a-9634-b87edc50e79e
    """
    serializer = UnsubscribeParamsLinkSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    
    data = serializer.save()
    
    email_settings = EmailSettings.objects.get(hash=data.settings_hash)
    
    return update_email_settings(data, email_settings, request=request)