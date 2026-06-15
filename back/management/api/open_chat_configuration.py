from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.helpers.has_open_chat_access import OpenChatConfigurationPermission
from management.models.open_chat_configuration import OpenChatConfiguration


class OpenChatConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpenChatConfiguration
        fields = ["open_chat_api_key", "open_chat_user", "open_chat_host"]
        extra_kwargs = {
            "open_chat_api_key": {"required": True},
            "open_chat_user": {"required": True},
            "open_chat_host": {"required": True},
        }


@extend_schema(
    methods=["GET"],
    responses=OpenChatConfigurationSerializer,
)
@extend_schema(
    methods=["POST"],
    request=OpenChatConfigurationSerializer,
    responses=OpenChatConfigurationSerializer,
)
@extend_schema(
    methods=["PUT"],
    request=OpenChatConfigurationSerializer,
    responses=OpenChatConfigurationSerializer,
)
@api_view(["GET", "POST", "PUT"])
@permission_classes([OpenChatConfigurationPermission])
@authentication_classes([SessionAuthentication])
def open_chat_configuration(request):
    if request.method == "GET":
        try:
            configuration = OpenChatConfiguration.objects.get(user=request.user)
        except OpenChatConfiguration.DoesNotExist:
            return Response(
                {"detail": "Open chat configuration not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OpenChatConfigurationSerializer(configuration).data)

    serializer = OpenChatConfigurationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if request.method == "POST":
        if OpenChatConfiguration.objects.filter(user=request.user).exists():
            return Response(
                {"detail": "Open chat configuration already exists. Use PUT to update."},
                status=status.HTTP_409_CONFLICT,
            )
        configuration = OpenChatConfiguration.objects.create(
            user=request.user,
            **serializer.validated_data,
        )
        return Response(
            OpenChatConfigurationSerializer(configuration).data,
            status=status.HTTP_201_CREATED,
        )

    try:
        configuration = OpenChatConfiguration.objects.get(user=request.user)
    except OpenChatConfiguration.DoesNotExist:
        return Response(
            {"detail": "Open chat configuration not found. Use POST to create."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = OpenChatConfigurationSerializer(configuration, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


api_urls = [
    path(
        "api/matching/open-chat-configuration/",
        open_chat_configuration,
        name="open_chat_configuration",
    ),
]
