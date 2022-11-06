import django.contrib.auth.password_validation as pw_validation
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from datetime import datetime
from django.conf import settings
from django.core import exceptions
from django.utils.module_loading import import_string
from rest_framework.decorators import api_view, schema, throttle_classes, permission_classes
from rest_framework import authentication, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from rest_framework import serializers
from rest_framework.throttling import UserRateThrottle
from rest_framework.permissions import IsAuthenticated
from ..models import ProfileSerializer, UserSerializer
from django.contrib.auth import get_user_model


class UserData(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAdminUser]
    """
    Returns the main application data for a given user.
    Basicly this is the data the main frontend app receives
    """
    # Waithin on 'async' support for DRF: https://github.com/encode/django-rest-framework/discussions/7774

    def get(self, request, format=None):
        return Response({
            "self": {
                "info": "self info",
                "profile": "profile",
                "state": "state"
            },
            "matches": [{
                "info": "some info placeholder",
                "profile": "some profile placeholder"
            }],
        })
