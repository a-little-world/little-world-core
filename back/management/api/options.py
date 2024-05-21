from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
import json
from back.utils import transform_add_options_serializer
from typing import Optional
from rest_framework import authentication, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from dataclasses import dataclass, field
from rest_framework import serializers
from django.core.paginator import Paginator
from rest_framework import status
from drf_spectacular.utils import extend_schema
from management.models.profile import SelfProfileSerializer
from management.controller import get_base_management_user
from django.conf import settings
from translations import get_translation_catalog


@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def get_options(request):
    """
    Get all notifications for the current user
    """
    """
    A helper tag that returns the api trasnlations  
    This can be used by frontends to dynamicly change error translation lanugages without resending requrests
    """
    translations = json.dumps(get_translation_catalog())
    
    bmu = get_base_management_user()

    ProfileWOptions = transform_add_options_serializer(SelfProfileSerializer)
    profile_data = ProfileWOptions(bmu.profile).data
    profile_options = profile_data["options"]

    return Response({
        "profile": profile_options,
    })