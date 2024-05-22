import datetime
import json
from rest_framework import serializers
from back.utils import CoolerJson
from rest_framework.views import APIView
from rest_framework import authentication, permissions, viewsets
from django.utils.translation import gettext_lazy as _
from django.utils import translation
from rest_framework.response import Response
from dataclasses import dataclass
from django.contrib.auth import authenticate, login
from drf_spectacular.utils import extend_schema
from management.api.user_data import frontend_data
from management.templatetags.temp_utils import get_api_translations
from management.models.profile import Profile, SelfProfileSerializer
from management.templatetags.temp_utils import get_api_translations
from management.views.cookie_banner_frontend import get_cookie_banner_template_data


@dataclass
class DevLoginInputData:
    username: str
    password: str
    dev_dataset: str


class DevLoginSerializer(serializers.Serializer):
    username = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)
    dev_dataset = serializers.CharField(required=True)

    def create(self, validated_data):
        return DevLoginAPI(**validated_data)


class DevLoginAPI(APIView):
    # WARNING: This should **never** be used in production
    # TODO: this should also maybe get some etra token security

    authentication_classes = []

    permission_classes = []

    @extend_schema(
        methods=["POST"],
        request=DevLoginSerializer(many=False)
    )
    def post(self, request):
        serializer = DevLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        if params.dev_dataset == "main_frontend":
            try:
                usr = authenticate(username=params.username,
                                   password=params.password)
                login(request, usr)
            except:
                return Response("Authentication failed", status=403)
            
            with translation.override("tag"):
                _frontend_data = frontend_data(usr)
                return Response({
                    "data": _frontend_data,
                    "api_translations": json.loads(get_api_translations(request))
                })
        return Response("Error, maybe dev_dataset doesn't exist?", status=400)
