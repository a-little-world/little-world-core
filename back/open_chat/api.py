import uuid as uuid_lib

from chat.models import Chat
from django.conf import settings
from django.db.models import Q
from django.urls import path
from drf_spectacular.utils import extend_schema, inline_serializer
from management import controller
from management.models.matches import Match
from management.models.profile import MinimalProfileSerializer
from management.models.support_task import SupportTask, SupportTaskAction
from management.models.user import User
from management.permissions import ManagementPermission
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from open_chat.helpers import (
    build_open_chat_client,
    exchange_open_chat_browser_token,
    resolve_open_chat_frontend_host,
    rewrite_open_chat_url_for_browser,
    value_or,
)
from open_chat.message_reply_suggestion import (
    idempotent_actions__generate_message_replies,
)
from open_chat.models import OpenChatConfiguration
from open_chat.permissions import (
    HasEditOpenChatConfiguration,
    HasManageOpenChatAccess,
    HasOpenChatAccess,
    HasOpenChatOrManageOpenChatAccess,
    OpenChatConfigurationPermission,
)
from open_chat.tool_definitions import sync_rest_tool_definitions


class OpenChatConfigurationSummarySerializer(serializers.ModelSerializer):
    open_chat_frontend_host = serializers.SerializerMethodField()

    class Meta:
        model = OpenChatConfiguration
        fields = [
            "open_chat_api_key",
            "open_chat_user",
            "open_chat_host",
            "open_chat_frontend_host",
        ]

    def get_open_chat_frontend_host(self, configuration: OpenChatConfiguration) -> str:
        return resolve_open_chat_frontend_host(configuration)


class OpenChatAccessUserSerializer(serializers.ModelSerializer):
    profile = MinimalProfileSerializer(read_only=True)
    configuration = serializers.SerializerMethodField()
    matching_exists = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["uuid", "id", "email", "profile", "configuration", "matching_exists"]

    def get_configuration(self, user):
        configuration = OpenChatConfiguration.objects.filter(user=user).first()
        if configuration is None:
            return None
        return OpenChatConfigurationSummarySerializer(configuration).data

    def get_matching_exists(self, user):
        manager_user = self.context.get("manager_user")
        if manager_user is None or user.pk == manager_user.pk:
            return None
        return Match.get_match(manager_user, user).exists()


class OpenChatConfigurationSerializer(serializers.ModelSerializer):
    open_chat_frontend_host = serializers.SerializerMethodField()
    matching_exists = serializers.SerializerMethodField()
    matching_user_uuid = serializers.SerializerMethodField()
    matching_user_id = serializers.SerializerMethodField()

    class Meta:
        model = OpenChatConfiguration
        fields = [
            "open_chat_api_key",
            "open_chat_user",
            "open_chat_host",
            "open_chat_frontend_host",
            "matching_exists",
            "matching_user_uuid",
            "matching_user_id",
        ]
        extra_kwargs = {
            "open_chat_api_key": {"required": True},
            "open_chat_user": {"required": True},
            "open_chat_host": {"required": True},
        }

    def get_open_chat_frontend_host(self, configuration: OpenChatConfiguration) -> str:
        return resolve_open_chat_frontend_host(configuration)

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

        partner = User.objects.filter(email=open_chat_automation_email).first()
        if partner is None or not Match.get_match(user, partner).exists():
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


def _parse_uuid(value: str) -> uuid_lib.UUID | None:
    try:
        return uuid_lib.UUID(value)
    except ValueError:
        return None


def _get_open_chat_access_user(user_id: int) -> User | None:
    user = User.objects.filter(pk=user_id).first()
    if user is None or not user.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
        return None
    return user


def _build_open_chat_bot_summary(bot) -> dict:
    default_config: dict = {}
    try:
        default_config = bot.default_config()
    except Exception:
        pass

    bot_data = getattr(bot, "data", None)
    description = None
    bot_username = None
    is_active = None
    is_public = None
    if bot_data is not None:
        description = value_or(getattr(bot_data, "description", None), None)
        bot_username = value_or(getattr(bot_data, "bot_username", None), None)
        is_active = value_or(getattr(bot_data, "is_active", None), None)
        is_public = value_or(getattr(bot_data, "is_public", None), None)

    return {
        "uuid": bot.uuid or None,
        "name": bot.name or None,
        "description": description,
        "bot_username": bot_username,
        "bot_user_uuid": bot.bot_user_uuid or None,
        "is_active": is_active,
        "is_public": is_public,
        "is_legacy_contact_bot": bool(getattr(bot, "is_legacy_contact_bot", False)),
        "model": default_config.get("model"),
        "default_shared_config": default_config or None,
    }


def _build_open_chat_interaction_state_summary(status) -> dict:
    latest_finished = value_or(getattr(status, "latest_message_finished", None), None)
    state = value_or(getattr(status, "state", None), None) or "idle"
    return {
        "chat_uuid": value_or(getattr(status, "chat_uuid", None), None),
        "is_active": bool(value_or(getattr(status, "is_active", None), False)),
        "state": state,
        "latest_message_uuid": value_or(getattr(status, "latest_message_uuid", None), None),
        "latest_message_finished": latest_finished,
        "source": value_or(getattr(status, "source", None), None),
    }


def _build_open_chat_interaction_summary(interaction, configuration=None) -> dict:
    try:
        raw_payload = interaction.to_dict()
    except Exception:
        raw_payload = {}

    interaction_id = str(value_or(interaction.uuid, ""))
    partner = value_or(interaction.partner, None)
    partner_name = value_or(partner.name, "") if partner is not None else ""
    title = partner_name or (f"Interaction {interaction_id}" if interaction_id else "Interaction")
    shared_url = value_or(interaction.shared_interaction_url, None)

    return {
        "interaction_id": interaction_id,
        "title": title,
        "created": None,
        "updated": None,
        "status": value_or(interaction.chat_type, None),
        "shared_interaction_url": rewrite_open_chat_url_for_browser(
            shared_url,
            configuration,
        ),
        "raw": raw_payload,
    }


def _open_chat_client_response(configuration, operation) -> Response:
    """Authenticate against the user's Open Chat host and map any client failure to a 502 response."""
    try:
        client = build_open_chat_client(configuration)
        login_user = client.login()
        return operation(client, login_user)
    except Exception as exc:
        return Response(
            {"detail": f"Open chat request failed: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )


def _resolve_open_chat_target_user(request) -> User | Response:
    target_user = request.user
    requested_user_uuid = (request.query_params.get("user_uuid") or "").strip()
    can_manage_open_chat_access = request.user.has_perm(ManagementPermission.MANAGE_OPEN_CHAT_ACCESS)

    if requested_user_uuid and can_manage_open_chat_access:
        parsed_uuid = _parse_uuid(requested_user_uuid)
        if parsed_uuid is None:
            return Response(
                {"detail": "Invalid user_uuid format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_self = parsed_uuid == request.user.uuid
        if not is_self:
            requested_user = User.objects.filter(uuid=parsed_uuid).first()
            if requested_user is None or not requested_user.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
                return Response(
                    {"detail": "Open chat access user not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            target_user = requested_user

    return target_user


OPEN_CHAT_BROWSER_TOKEN_SCOPES = frozenset(
    {
        "bots:read",
        "bots:write",
        "interactions:list",
        "interactions:read",
    }
)


class OpenChatBrowserTokenRequestSerializer(serializers.Serializer):
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(OPEN_CHAT_BROWSER_TOKEN_SCOPES)),
        allow_empty=False,
    )

    def validate_scopes(self, scopes: list[str]) -> list[str]:
        return list(dict.fromkeys(scopes))


def _get_open_chat_idempotent_action_specs() -> list[dict]:
    return [
        {
            "idempotent_action": "idempotent_actions__generate_message_replies",
            "title": "Generate message replies",
            "description": (
                "Finds latest unreplied user messages, creates support reply tasks,"
                " and enqueues Open Chat interaction generation."
            ),
            "trigger_endpoint": "/api/matching/open-chat/automation-triggers/generate-message-replies/",
            "trigger_method": "POST",
            "clear_endpoint": "/api/matching/open-chat/automation-triggers/generate-message-replies/clear/",
            "clear_method": "DELETE",
            "support_task_action_types": ["support_reply"],
            "support_task_filters": {
                "status": [SupportTask.Status.NEW, SupportTask.Status.IN_PROGRESS],
                "action_type": ["support_reply"],
            },
        }
    ]


def _build_open_chat_idempotent_actions_response(target_user: User) -> list[dict]:
    action_specs = _get_open_chat_idempotent_action_specs()
    open_statuses = [SupportTask.Status.NEW, SupportTask.Status.IN_PROGRESS]
    results: list[dict] = []

    for spec in action_specs:
        action_types = spec.get("support_task_action_types", [])
        relation_qs = SupportTaskAction.objects.filter(
            action_type__in=action_types,
            status=SupportTaskAction.Status.OPEN,
            task__status__in=open_statuses,
            static_parameters__kind_display="Open Chat",
            static_parameters__recipient_user_id=target_user.pk,
        )
        results.append(
            {
                "idempotent_action": spec["idempotent_action"],
                "title": spec["title"],
                "description": spec["description"],
                "trigger_endpoint": spec["trigger_endpoint"],
                "trigger_method": spec["trigger_method"],
                "clear_endpoint": spec["clear_endpoint"],
                "clear_method": spec["clear_method"],
                "support_task_relation": {
                    "action_types": action_types,
                    "open_statuses": open_statuses,
                    "open_count": relation_qs.count(),
                    "suggested_filters": spec["support_task_filters"],
                },
            }
        )
    return results


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
        configuration = OpenChatConfiguration.objects.filter(user=request.user).first()
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

    configuration = OpenChatConfiguration.objects.filter(user=request.user).first()
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
    request=OpenChatBrowserTokenRequestSerializer,
    responses=inline_serializer(
        name="OpenChatBrowserTokenResponse",
        fields={
            "access_token": serializers.CharField(),
            "token_type": serializers.CharField(),
            "expires_at": serializers.DateTimeField(),
            "expires_in": serializers.IntegerField(),
            "scopes": serializers.ListField(child=serializers.CharField()),
            "api_base_url": serializers.URLField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([HasOpenChatOrManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_browser_token(request):
    request_serializer = OpenChatBrowserTokenRequestSerializer(data=request.data)
    request_serializer.is_valid(raise_exception=True)
    scopes = request_serializer.validated_data["scopes"]

    if "bots:write" in scopes and not request.user.has_perm(ManagementPermission.EDIT_OPEN_CHAT_CONFIGURATION):
        return Response(
            {"detail": "You do not have permission to edit Open Chat bots."},
            status=status.HTTP_403_FORBIDDEN,
        )

    target_user = _resolve_open_chat_target_user(request)
    if isinstance(target_user, Response):
        return target_user
    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        token_payload = exchange_open_chat_browser_token(
            configuration,
            scopes=scopes,
            label=f"little-world-admin:{request.user.uuid}",
        )
    except Exception as exc:
        return Response(
            {"detail": f"Open chat browser authorization failed: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    response = Response(
        {
            **token_payload,
            "token_type": token_payload.get("token_type") or "Bearer",
            "scopes": token_payload.get("scopes") or scopes,
            "api_base_url": resolve_open_chat_frontend_host(configuration),
        }
    )
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


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
    configuration = OpenChatConfiguration.objects.filter(user=request.user).first()
    if configuration is None:
        return Response(
            {"success": False, "detail": "Open chat configuration not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    def respond(_client, login_user):
        user_name = login_user.name
        return Response(
            {
                "success": True,
                "user_name": user_name,
                "detail": f"Successfully logged in as {user_name or configuration.open_chat_user}.",
            }
        )

    return _open_chat_client_response(configuration, respond)


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

    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
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


@extend_schema(
    methods=["DELETE"],
    responses=inline_serializer(
        name="OpenChatDeleteChatResponse",
        fields={
            "chat_uuid": serializers.UUIDField(),
            "detail": serializers.CharField(),
        },
    ),
)
@api_view(["DELETE"])
@permission_classes([HasOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_delete_chat(request, chat_uuid: str):
    parsed_chat_uuid = _parse_uuid(chat_uuid)
    if parsed_chat_uuid is None:
        return Response(
            {"detail": "Invalid chat UUID format."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    chat = (
        Chat.objects.filter(
            uuid=parsed_chat_uuid,
            is_temporary=False,
        )
        .filter(
            Q(u1=request.user) | Q(u2=request.user),
        )
        .first()
    )
    if chat is None:
        return Response(
            {"detail": "Open chat not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    partner = chat.get_partner(request.user)
    if not partner.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
        return Response(
            {"detail": "Chat partner does not have open chat access."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    deleted_chat_uuid = str(chat.uuid)
    chat.delete()
    return Response(
        {"chat_uuid": deleted_chat_uuid, "detail": "Chat deleted."},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    methods=["GET"],
    responses=inline_serializer(
        name="OpenChatBotsResponse",
        fields={
            "results": inline_serializer(
                name="OpenChatBotSummary",
                many=True,
                fields={
                    "uuid": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "name": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "description": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "bot_username": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "bot_user_uuid": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "is_active": serializers.BooleanField(required=False, allow_null=True),
                    "is_public": serializers.BooleanField(required=False, allow_null=True),
                    "is_legacy_contact_bot": serializers.BooleanField(),
                    "model": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "default_shared_config": serializers.JSONField(required=False, allow_null=True),
                },
            )
        },
    ),
)
@api_view(["GET"])
@permission_classes([HasOpenChatOrManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_bots(request):
    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    def respond(client, _login_user):
        bots = [_build_open_chat_bot_summary(bot) for bot in client.list_owned_bots()]
        return Response({"results": bots})

    return _open_chat_client_response(configuration, respond)


class OpenChatBotUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_active = serializers.BooleanField(required=False)
    is_public = serializers.BooleanField(required=False)
    default_shared_config = serializers.JSONField(required=False)


def _merge_bot_default_shared_config(client, bot_identifier: str, patch: dict | None) -> dict | None:
    if patch is None:
        return None
    existing = client.get_bot(bot_identifier).default_config()
    return {**existing, **patch}


@extend_schema(
    methods=["PATCH"],
    request=OpenChatBotUpdateSerializer,
    responses=inline_serializer(
        name="OpenChatBotDetailResponse",
        fields={
            "uuid": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "name": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "description": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "bot_username": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "bot_user_uuid": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "is_active": serializers.BooleanField(required=False, allow_null=True),
            "is_public": serializers.BooleanField(required=False, allow_null=True),
            "is_legacy_contact_bot": serializers.BooleanField(),
            "model": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "default_shared_config": serializers.JSONField(required=False, allow_null=True),
        },
    ),
)
@api_view(["PATCH"])
@permission_classes([HasEditOpenChatConfiguration])
@authentication_classes([SessionAuthentication])
def open_chat_bot_detail(request, bot_identifier: str):
    if not bot_identifier.strip():
        return Response(
            {"detail": "Bot identifier is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = OpenChatBotUpdateSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data
    if not validated:
        return Response(
            {"detail": "No bot fields provided to update."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def respond(client, _login_user):
        update_kwargs: dict = {}
        if "name" in validated:
            update_kwargs["name"] = validated["name"]
        if "description" in validated:
            update_kwargs["description"] = validated["description"]
        if "is_active" in validated:
            update_kwargs["is_active"] = validated["is_active"]
        if "is_public" in validated:
            update_kwargs["is_public"] = validated["is_public"]
        if "default_shared_config" in validated:
            update_kwargs["default_shared_config"] = _merge_bot_default_shared_config(
                client,
                bot_identifier,
                validated["default_shared_config"],
            )

        updated = client.update_bot(bot_identifier, **update_kwargs)
        return Response(_build_open_chat_bot_summary(updated))

    return _open_chat_client_response(configuration, respond)


@extend_schema(
    methods=["GET"],
    responses=inline_serializer(
        name="OpenChatInteractionsResponse",
        fields={
            "results": inline_serializer(
                name="OpenChatInteraction",
                many=True,
                fields={
                    "interaction_id": serializers.CharField(),
                    "title": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "created": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "updated": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "status": serializers.CharField(required=False, allow_blank=True, allow_null=True),
                    "shared_interaction_url": serializers.CharField(
                        required=False,
                        allow_blank=True,
                        allow_null=True,
                    ),
                    "raw": serializers.JSONField(required=False),
                },
            )
        },
    ),
)
@api_view(["GET"])
@permission_classes([HasOpenChatOrManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_interactions(request):
    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    def respond(client, _login_user):
        interactions = [
            _build_open_chat_interaction_summary(item, configuration)
            for item in value_or(client.get_interactions().rows, [])
        ]
        return Response({"results": interactions})

    return _open_chat_client_response(configuration, respond)


@extend_schema(
    methods=["GET"],
    responses=inline_serializer(
        name="OpenChatInteractionStateResponse",
        fields={
            "chat_uuid": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "is_active": serializers.BooleanField(),
            "state": serializers.CharField(),
            "latest_message_uuid": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "latest_message_finished": serializers.BooleanField(required=False, allow_null=True),
            "source": serializers.CharField(required=False, allow_blank=True, allow_null=True),
        },
    ),
)
@api_view(["GET"])
@permission_classes([HasOpenChatOrManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_interaction_state(request, interaction_share_uuid: str):
    if _parse_uuid(interaction_share_uuid) is None:
        return Response(
            {"detail": "Invalid interaction share UUID format."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    def respond(client, _login_user):
        return Response(
            _build_open_chat_interaction_state_summary(client.get_shared_interaction_status(interaction_share_uuid))
        )

    return _open_chat_client_response(configuration, respond)


@extend_schema(
    methods=["GET"],
    responses=inline_serializer(
        name="OpenChatInteractionDetailResponse",
        fields={
            "interaction_id": serializers.CharField(),
            "title": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "created": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "updated": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "status": serializers.CharField(required=False, allow_blank=True, allow_null=True),
            "shared_interaction_url": serializers.CharField(
                required=False,
                allow_blank=True,
                allow_null=True,
            ),
            "raw": serializers.JSONField(required=False),
        },
    ),
)
@api_view(["GET"])
@permission_classes([HasOpenChatOrManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_interaction_detail(request, interaction_uuid: str):
    if _parse_uuid(interaction_uuid) is None:
        return Response(
            {"detail": "Invalid interaction UUID format."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    def respond(client, _login_user):
        return Response(
            _build_open_chat_interaction_summary(
                client.get_interaction(interaction_uuid),
                configuration,
            )
        )

    return _open_chat_client_response(configuration, respond)


@extend_schema(
    methods=["GET"],
    responses=inline_serializer(
        name="OpenChatIdempotentActionsResponse",
        fields={
            "target_user_uuid": serializers.UUIDField(),
            "results": inline_serializer(
                name="OpenChatIdempotentAction",
                many=True,
                fields={
                    "idempotent_action": serializers.CharField(),
                    "title": serializers.CharField(),
                    "description": serializers.CharField(),
                    "trigger_endpoint": serializers.CharField(),
                    "trigger_method": serializers.CharField(),
                    "clear_endpoint": serializers.CharField(),
                    "clear_method": serializers.CharField(),
                    "support_task_relation": inline_serializer(
                        name="OpenChatIdempotentActionSupportTaskRelation",
                        fields={
                            "action_types": serializers.ListField(child=serializers.CharField()),
                            "open_statuses": serializers.ListField(child=serializers.CharField()),
                            "open_count": serializers.IntegerField(),
                            "suggested_filters": serializers.JSONField(),
                        },
                    ),
                },
            ),
        },
    ),
)
@api_view(["GET"])
@permission_classes([HasOpenChatOrManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_idempotent_actions(request):
    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    return Response(
        {
            "target_user_uuid": str(target_user.uuid),
            "results": _build_open_chat_idempotent_actions_response(target_user),
        }
    )


@extend_schema(
    methods=["POST"],
    responses=inline_serializer(
        name="OpenChatAutomationGenerateMessageRepliesResponse",
        fields={
            "trigger": serializers.CharField(),
            "task_id": serializers.CharField(),
            "target_user_uuid": serializers.UUIDField(),
            "detail": serializers.CharField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([HasOpenChatOrManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_automation_generate_message_replies(request):
    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    task = idempotent_actions__generate_message_replies.delay(  # pyright: ignore[reportCallIssue]
        target_user_uuid=str(target_user.uuid),
        triggered_by_user_uuid=str(request.user.uuid),
    )
    return Response(
        {
            "trigger": "idempotent_actions__generate_message_replies",
            "task_id": task.id,
            "target_user_uuid": str(target_user.uuid),
            "detail": "Automation trigger enqueued.",
        },
        status=status.HTTP_202_ACCEPTED,
    )


@extend_schema(
    methods=["DELETE"],
    responses=inline_serializer(
        name="OpenChatAutomationClearMessageRepliesResponse",
        fields={
            "trigger": serializers.CharField(),
            "target_user_uuid": serializers.UUIDField(),
            "deleted_support_tasks_count": serializers.IntegerField(),
            "deleted_support_task_actions_count": serializers.IntegerField(),
            "detail": serializers.CharField(),
        },
    ),
)
@api_view(["DELETE"])
@permission_classes([HasOpenChatOrManageOpenChatAccess])
@authentication_classes([SessionAuthentication])
def open_chat_automation_clear_message_replies(request):
    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    related_actions_qs = SupportTaskAction.objects.filter(
        action_type="support_reply",
        static_parameters__kind_display="Open Chat",
        static_parameters__recipient_user_id=target_user.pk,
    ).exclude(task__status=SupportTask.Status.COMPLETED)
    deleted_actions_count = related_actions_qs.count()
    related_task_ids = list(related_actions_qs.values_list("task_id", flat=True).distinct())
    deleted_tasks_count = len(related_task_ids)
    if related_task_ids:
        SupportTask.objects.filter(pk__in=related_task_ids).delete()

    return Response(
        {
            "trigger": "idempotent_actions__generate_message_replies.clear",
            "target_user_uuid": str(target_user.uuid),
            "deleted_support_tasks_count": deleted_tasks_count,
            "deleted_support_task_actions_count": deleted_actions_count,
            "detail": "Related support tasks deleted.",
        }
    )


class OpenChatRestToolsSyncRequestSerializer(serializers.Serializer):
    reload = serializers.BooleanField(required=False, default=False)


@extend_schema(
    methods=["POST"],
    request=OpenChatRestToolsSyncRequestSerializer,
    responses=inline_serializer(
        name="OpenChatRestToolsSyncResponse",
        fields={
            "target_user_uuid": serializers.UUIDField(),
            "reload": serializers.BooleanField(),
            "created": serializers.ListField(child=serializers.CharField()),
            "updated": serializers.ListField(child=serializers.CharField()),
            "deleted": serializers.ListField(child=serializers.CharField()),
            "detail": serializers.CharField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([HasEditOpenChatConfiguration])
@authentication_classes([SessionAuthentication])
def open_chat_sync_rest_tools(request):
    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    configuration = OpenChatConfiguration.objects.filter(user=target_user).first()
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = OpenChatRestToolsSyncRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    reload = bool(serializer.validated_data.get("reload", False))

    def respond(client, _login_user):
        sync_result = sync_rest_tool_definitions(client, reload=reload)
        action = "reloaded" if reload else "synced"
        return Response(
            {
                "target_user_uuid": str(target_user.uuid),
                "reload": reload,
                **sync_result,
                "detail": f"REST API tools {action} on Open Chat.",
            }
        )

    return _open_chat_client_response(configuration, respond)


api_urls = [
    path(
        "api/matching/open-chat-configuration/",
        open_chat_configuration,
        name="open_chat_configuration",
    ),
    path(
        "api/matching/open-chat/browser-token/",
        open_chat_browser_token,
        name="open_chat_browser_token",
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
    path(
        "api/matching/open-chat/chats/<str:chat_uuid>/",
        open_chat_delete_chat,
        name="open_chat_delete_chat",
    ),
    path(
        "api/matching/open-chat/bots/",
        open_chat_bots,
        name="open_chat_bots",
    ),
    path(
        "api/matching/open-chat/bots/<str:bot_identifier>/",
        open_chat_bot_detail,
        name="open_chat_bot_detail",
    ),
    path(
        "api/matching/open-chat/interactions/",
        open_chat_interactions,
        name="open_chat_interactions",
    ),
    path(
        "api/matching/open-chat/interactions/<str:interaction_share_uuid>/state/",
        open_chat_interaction_state,
        name="open_chat_interaction_state",
    ),
    path(
        "api/matching/open-chat/interactions/<str:interaction_uuid>/",
        open_chat_interaction_detail,
        name="open_chat_interaction_detail",
    ),
    path(
        "api/matching/open-chat/idempotent-actions/",
        open_chat_idempotent_actions,
        name="open_chat_idempotent_actions",
    ),
    path(
        "api/matching/open-chat/automation-triggers/generate-message-replies/",
        open_chat_automation_generate_message_replies,
        name="open_chat_automation_generate_message_replies",
    ),
    path(
        "api/matching/open-chat/automation-triggers/generate-message-replies/clear/",
        open_chat_automation_clear_message_replies,
        name="open_chat_automation_clear_message_replies",
    ),
    path(
        "api/matching/open-chat/rest-tools/sync/",
        open_chat_sync_rest_tools,
        name="open_chat_sync_rest_tools",
    ),
]
