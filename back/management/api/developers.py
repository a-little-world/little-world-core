from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from dataclasses import dataclass
from django.contrib.auth import authenticate, login
from drf_spectacular.utils import extend_schema
from management.api.user_data import frontend_data
from translations import get_translation_catalog


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

    @extend_schema(methods=["POST"], request=DevLoginSerializer(many=False))
    def post(self, request):
        serializer = DevLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        if params.dev_dataset == "main_frontend":
            try:
                usr = authenticate(username=params.username, password=params.password)
                login(request, usr)
            except:
                return Response("Authentication failed", status=403)

            _frontend_data = frontend_data(usr)
            return Response({"data": _frontend_data, "api_translations": get_translation_catalog()})
        return Response("Error, maybe dev_dataset doesn't exist?", status=400)
