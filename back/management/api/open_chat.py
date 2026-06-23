from chat.models import Chat
from django.conf import settings
from django.urls import path
from drf_spectacular.utils import extend_schema, inline_serializer
from requests import RequestException
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management import controller
from management.helpers.has_open_chat_access import (
    HasManageOpenChatAccess,
    HasOpenChatAccess,
    OpenChatConfigurationPermission,
)
from management.models.matches import Match
from management.models.open_chat_configuration import OpenChatConfiguration
from management.models.profile import MinimalProfileSerializer
from management.models.user import User
from management.permissions import ManagementPermission


class OpenChatConfigurationSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = OpenChatConfiguration
        fields = ["open_chat_api_key", "open_chat_user", "open_chat_host"]


class OpenChatAccessUserSerializer(serializers.ModelSerializer):
    profile = MinimalProfileSerializer(read_only=True)
    configuration = serializers.SerializerMethodField()
    matching_exists = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["uuid", "id", "email", "profile", "configuration", "matching_exists"]

    def get_configuration(self, user):
        try:
            configuration = user.open_chat_configuration
        except OpenChatConfiguration.DoesNotExist:
            return None
        return OpenChatConfigurationSummarySerializer(configuration).data

    def get_matching_exists(self, user):
        manager_user = self.context.get("manager_user")
        if manager_user is None or user.pk == manager_user.pk:
            return None
        return Match.get_match(manager_user, user).exists()


class OpenChatConfigurationSerializer(serializers.ModelSerializer):
    matching_exists = serializers.SerializerMethodField()
    matching_user_uuid = serializers.SerializerMethodField()
    matching_user_id = serializers.SerializerMethodField()

    class Meta:
        model = OpenChatConfiguration
        fields = [
            "open_chat_api_key",
            "open_chat_user",
            "open_chat_host",
            "interaction_overwrite",
            "matching_exists",
            "matching_user_uuid",
            "matching_user_id",
        ]
        extra_kwargs = {
            "open_chat_api_key": {"required": True},
            "open_chat_user": {"required": True},
            "open_chat_host": {"required": True},
            "interaction_overwrite": {"required": False},
        }

    def _get_matching_partner(self, configuration: OpenChatConfiguration) -> User | None:
        if hasattr(self, "_matching_partner"):
            return self._matching_partner

        request = self.context.get("request")
        if request is None:
            self._matching_partner = None
            return None

        user = request.user
        open_chat_automation_email = getattr(settings, "OPEN_CHAT_AUTOMATION_USER_EMAIL", None)
        if not open_chat_automation_email:
            self._matching_partner = None
            return None

        try:
            partner = User.objects.get(email=open_chat_automation_email)
        except User.DoesNotExist:
            self._matching_partner = None
            return None

        if not Match.get_match(user, partner).exists():
            self._matching_partner = None
            return None

        self._matching_partner = partner
        return partner

    def get_matching_exists(self, configuration: OpenChatConfiguration):
        return self._get_matching_partner(configuration) is not None

    def get_matching_user_uuid(self, configuration: OpenChatConfiguration):
        partner = self._get_matching_partner(configuration)
        return str(partner.uuid) if partner else None

    def get_matching_user_id(self, configuration: OpenChatConfiguration):
        partner = self._get_matching_partner(configuration)
        return partner.pk if partner else None


def _get_user_configuration(user) -> OpenChatConfiguration | None:
    try:
        return OpenChatConfiguration.objects.get(user=user)
    except OpenChatConfiguration.DoesNotExist:
        return None


def _get_open_chat_access_user(user_id: int) -> User | None:
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None
    if not user.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
        return None
    return user


def _build_open_chat_client(host: str, username: str, password: str):
    from client.client import OpenChatPythonClient

    return OpenChatPythonClient(host=host, username=username, password=password)


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
        configuration = _get_user_configuration(request.user)
        if configuration is None:
            return Response(
                {"detail": "Open chat configuration not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OpenChatConfigurationSerializer(configuration, context={"request": request}).data)

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
            OpenChatConfigurationSummarySerializer(configuration).data,
            status=status.HTTP_201_CREATED,
        )

    configuration = _get_user_configuration(request.user)
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found. Use POST to create."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = OpenChatConfigurationSerializer(configuration, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(OpenChatConfigurationSummarySerializer(configuration).data)


@extend_schema(
    methods=["POST"],
    responses=inline_serializer(
        name="OpenChatTestConnectionResponse",
        fields={
            "success": serializers.BooleanField(),
            "user_name": serializers.CharField(required=False),
            "detail": serializers.CharField(required=False),
        },
    ),
)
@api_view(["POST"])
@permission_classes([HasOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_test_connection(request):
    configuration = _get_user_configuration(request.user)
    if configuration is None:
        return Response(
            {"success": False, "detail": "Open chat configuration not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        client = _build_open_chat_client(
            host=configuration.open_chat_host,
            username=configuration.open_chat_user,
            password=configuration.open_chat_api_key,
        )
        user = client.login()
        user_name = user.get("name") if isinstance(user, dict) else None
        return Response(
            {
                "success": True,
                "user_name": user_name,
                "detail": f"Successfully logged in as {user_name or configuration.open_chat_user}.",
            }
        )
    except ImportError as exc:
        return Response(
            {
                "success": False,
                "detail": f"Open chat client is not installed: {exc}",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except RequestException as exc:
        return Response(
            {
                "success": False,
                "detail": f"Open chat login request failed: {exc}",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception as exc:
        return Response(
            {
                "success": False,
                "detail": f"Open chat connection test failed: {exc}",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )


@extend_schema(
    methods=["GET"],
    responses=OpenChatAccessUserSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([HasManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_access_users(request):
    users = (
        User.objects.filter(
            user_permissions__codename=ManagementPermission.OPEN_CHAT_ACCESS.codename,
            user_permissions__content_type__app_label="management",
            user_permissions__content_type__model="state",
        )
        .distinct()
        .select_related("profile", "open_chat_configuration")
        .order_by("-date_joined")
    )
    serializer = OpenChatAccessUserSerializer(
        users,
        many=True,
        context={"manager_user": request.user},
    )
    return Response(serializer.data)


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
@api_view(["POST", "PUT"])
@permission_classes([HasManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_user_configuration(request, user_id: int):
    target_user = _get_open_chat_access_user(user_id)
    if target_user is None:
        return Response(
            {"detail": "Open chat access user not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = OpenChatConfigurationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if request.method == "POST":
        if OpenChatConfiguration.objects.filter(user=target_user).exists():
            return Response(
                {"detail": "Open chat configuration already exists. Use PUT to update."},
                status=status.HTTP_409_CONFLICT,
            )
        configuration = OpenChatConfiguration.objects.create(
            user=target_user,
            **serializer.validated_data,
        )
        return Response(
            OpenChatConfigurationSummarySerializer(configuration).data,
            status=status.HTTP_201_CREATED,
        )

    configuration = _get_user_configuration(target_user)
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found. Use POST to create."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = OpenChatConfigurationSerializer(configuration, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(OpenChatConfigurationSummarySerializer(configuration).data)


@extend_schema(
    methods=["POST"],
    responses=inline_serializer(
        name="OpenChatCreateMatchingResponse",
        fields={
            "matching_exists": serializers.BooleanField(),
            "match_uuid": serializers.UUIDField(required=False),
            "detail": serializers.CharField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([HasManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_create_matching(request, user_id: int):
    target_user = _get_open_chat_access_user(user_id)
    if target_user is None:
        return Response(
            {"detail": "Open chat access user not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if target_user.pk == request.user.pk:
        return Response(
            {"detail": "Cannot create a matching with yourself."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if Match.get_match(request.user, target_user).exists():
        return Response(
            {
                "matching_exists": True,
                "detail": "Matching already exists.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    try:
        matching = controller.match_users(
            {request.user, target_user},
            send_notification=False,
            send_message=False,
            send_email=False,
            set_unconfirmed=False,
        )
    except Exception as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "matching_exists": True,
            "match_uuid": matching.uuid,
            "detail": "Matching created.",
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    methods=["POST"],
    responses=inline_serializer(
        name="OpenChatCreateChatResponse",
        fields={
            "chat_uuid": serializers.UUIDField(),
            "chat_created": serializers.BooleanField(),
            "detail": serializers.CharField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([HasOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_create_chat(request, user_id: int):
    target_user = _get_open_chat_access_user(user_id)
    if target_user is None:
        return Response(
            {"detail": "Open chat access user not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if target_user.pk == request.user.pk:
        return Response(
            {"detail": "Cannot create a chat with yourself."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    can_manage_open_chat_access = request.user.has_perm(ManagementPermission.MANAGE_OPEN_CHAT_ACCESS)
    if not can_manage_open_chat_access:
        if target_user.email != settings.OPEN_CHAT_AUTOMATION_USER_EMAIL:
            return Response(
                {"detail": "You can only create chats with the configured Open Chat automation user."},
                status=status.HTTP_403_FORBIDDEN,
            )

    if not Match.get_match(request.user, target_user).exists():
        return Response(
            {"detail": "No active matching exists between these users."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    chat = Chat.objects.create(u1=request.user, u2=target_user, is_temporary=False)
    chat_created = True

    return Response(
        {
            "chat_uuid": chat.uuid,
            "chat_created": chat_created,
            "detail": "Chat created." if chat_created else "Chat already exists.",
        },
        status=status.HTTP_201_CREATED if chat_created else status.HTTP_200_OK,
    )


api_urls = [
    path(
        "api/matching/open-chat-configuration/",
        open_chat_configuration,
        name="open_chat_configuration",
    ),
    path(
        "api/matching/open-chat/test-connection/",
        open_chat_test_connection,
        name="open_chat_test_connection",
    ),
    path(
        "api/matching/open-chat-access-users/",
        open_chat_access_users,
        name="open_chat_access_users",
    ),
    path(
        "api/matching/open-chat-access-users/<int:user_id>/configuration/",
        open_chat_user_configuration,
        name="open_chat_user_configuration",
    ),
    path(
        "api/matching/open-chat-access-users/<int:user_id>/create-matching/",
        open_chat_create_matching,
        name="open_chat_create_matching",
    ),
    path(
        "api/matching/open-chat-access-users/<int:user_id>/create-chat/",
        open_chat_create_chat,
        name="open_chat_create_chat",
    ),
]
