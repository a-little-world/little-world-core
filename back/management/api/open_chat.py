import uuid as uuid_lib

from chat.models import Chat
from client.client import OpenChatPythonClient
from django.conf import settings
from django.db.models import Q
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
    HasOpenChatOrManageOpenChatAccess,
    OpenChatConfigurationPermission,
)
from management.models.matches import Match
from management.models.open_chat_configuration import OpenChatConfiguration
from management.models.profile import MinimalProfileSerializer
from management.models.support_task import SupportTask, SupportTaskAction
from management.models.user import User
from management.open_chat_interaction_task import idempotent_actions__generate_message_replies
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


def _get_open_chat_access_user_by_uuid(user_uuid: str) -> User | None:
    try:
        parsed_uuid = uuid_lib.UUID(user_uuid)
    except ValueError:
        return None

    user = User.objects.filter(uuid=parsed_uuid).first()
    if user is None:
        return None
    if not user.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
        return None
    return user


def _build_open_chat_client(host: str, username: str, password: str):
    return OpenChatPythonClient(host=host, username=username, password=password)


def _build_open_chat_interaction_summary(interaction) -> dict:
    try:
        raw_payload = interaction.to_dict()
    except Exception:
        raw_payload = {}

    return {
        "interaction_id": str(interaction.uuid),
        "title": interaction.title,
        "created": interaction.created,
        "updated": interaction.updated,
        "status": interaction.status,
        "shared_interaction_url": interaction.shared_interaction_url,
        "raw": raw_payload,
    }


def _fetch_open_chat_interactions(client) -> list[dict]:
    payload = client.get_interactions()
    rows = payload.rows
    return [_build_open_chat_interaction_summary(item) for item in rows]


def _fetch_open_chat_interaction(client, interaction_uuid: str) -> dict:
    payload = client.get_interaction(interaction_uuid)
    return _build_open_chat_interaction_summary(payload)


def _resolve_open_chat_target_user(request) -> User | Response:
    target_user = request.user
    requested_user_uuid = (request.query_params.get("user_uuid") or "").strip()
    can_manage_open_chat_access = request.user.has_perm(ManagementPermission.MANAGE_OPEN_CHAT_ACCESS)

    if requested_user_uuid and can_manage_open_chat_access:
        try:
            parsed_uuid = uuid_lib.UUID(requested_user_uuid)
        except ValueError:
            return Response(
                {"detail": "Invalid user_uuid format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_self = parsed_uuid == request.user.uuid
        if not is_self:
            requested_user = _get_open_chat_access_user_by_uuid(requested_user_uuid)
            if requested_user is None:
                return Response(
                    {"detail": "Open chat access user not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            target_user = requested_user

    return target_user


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
        user_name = user.name
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
    try:
        parsed_chat_uuid = uuid_lib.UUID(chat_uuid)
    except ValueError:
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

    configuration = _get_user_configuration(target_user)
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        client = _build_open_chat_client(
            host=configuration.open_chat_host,
            username=configuration.open_chat_user,
            password=configuration.open_chat_api_key,
        )
        client.login()
        interactions = _fetch_open_chat_interactions(client)
        return Response({"results": interactions})
    except ImportError as exc:
        return Response(
            {"detail": f"Open chat client is not installed: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except RequestException as exc:
        return Response(
            {"detail": f"Open chat interaction request failed: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception as exc:
        return Response(
            {"detail": f"Could not load open chat interactions: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )


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
    try:
        uuid_lib.UUID(interaction_uuid)
    except ValueError:
        return Response(
            {"detail": "Invalid interaction UUID format."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target_user_or_response = _resolve_open_chat_target_user(request)
    if isinstance(target_user_or_response, Response):
        return target_user_or_response
    target_user = target_user_or_response

    configuration = _get_user_configuration(target_user)
    if configuration is None:
        return Response(
            {"detail": "Open chat configuration not found for target user."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        client = _build_open_chat_client(
            host=configuration.open_chat_host,
            username=configuration.open_chat_user,
            password=configuration.open_chat_api_key,
        )
        client.login()
        interaction = _fetch_open_chat_interaction(client, interaction_uuid)
        return Response(interaction)
    except ImportError as exc:
        return Response(
            {"detail": f"Open chat client is not installed: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except RequestException as exc:
        return Response(
            {"detail": f"Open chat interaction detail request failed: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception as exc:
        return Response(
            {"detail": f"Could not load open chat interaction detail: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )


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

    configuration = _get_user_configuration(target_user)
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
    )
    deleted_actions_count = related_actions_qs.count()
    related_task_ids = list(related_actions_qs.values_list("task_id", flat=True))
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
    path(
        "api/matching/open-chat/chats/<str:chat_uuid>/",
        open_chat_delete_chat,
        name="open_chat_delete_chat",
    ),
    path(
        "api/matching/open-chat/interactions/",
        open_chat_interactions,
        name="open_chat_interactions",
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
]
