import uuid as uuid_lib

from celery import current_app
from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from management.helpers import DetailedPaginationMixin, UserStaffRestricedModelViewsetMixin
from management.models.user import User
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from chat.helpers import MatchSendForbidden, MessageSendValidationError, create_and_deliver_message
from chat.models import Chat, Message, MessageSerializer


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100


class SendAttachmentSerializer(serializers.Serializer):
    file = serializers.FileField()


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(required=False)


class MessagesModelViewSet(UserStaffRestricedModelViewsetMixin, viewsets.ModelViewSet):
    """
    Simple Viewset messages CREATE, LIST, UPDATE, DELETE
    """

    allow_user_list = True
    not_user_editable = MessageSerializer.Meta.fields  # For users all fields are ready only on this one!
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DetailedPaginationMixin
    queryset = Message.objects.all().order_by("created")
    resp_chat_403 = Response({"error": "Chat doesn't exist or you have no permission to interact with it!"}, status=403)

    @staticmethod
    def _is_valid_uuid(value: str | None) -> bool:
        if not value:
            return False
        try:
            uuid_lib.UUID(value)
            return True
        except ValueError:
            return False

    def filter_queryset(self, queryset):
        if hasattr(self, "chat_uuid"):
            if self.request.user.is_staff:
                chat = Chat.objects.filter(uuid=self.chat_uuid).first()
            else:
                chat = Chat.objects.filter(
                    Q(u1=self.request.user) | Q(u2=self.request.user), uuid=self.chat_uuid
                ).first()
            if chat is None:
                return Message.objects.none()
            return chat.get_messages().order_by("-created")
        return super().filter_queryset(queryset)

    def list(self, request, *args, **kwargs):
        if "chat_uuid" in kwargs:
            chat_uuid = kwargs["chat_uuid"]
            if not self._is_valid_uuid(chat_uuid):
                return Response({"error": "chat_uuid is not a valid UUID"}, status=400)
            self.chat_uuid = chat_uuid
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Message.objects.filter(chat__in=Chat.get_chats(self.request.user))
            .select_related("sender", "recipient")
            .order_by("-created")
        )

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        if not obj.chat.is_participant(request.user):
            return self.resp_chat_403
        if not ((obj.sender != request.user) and (obj.recipient == request.user)):
            return Response({"error": "You can't mark this message as read!"}, status=400)

        obj.read = True
        obj.save()
        return Response(self.get_serializer(obj).data, status=200)

    @extend_schema(request=SendMessageSerializer)
    @action(detail=False, methods=["post"])
    def chat_read(self, request, chat_uuid=None):
        if not chat_uuid:
            return Response({"error": "chat_uuid is required"}, status=400)
        if not self._is_valid_uuid(chat_uuid):
            return Response({"error": "chat_uuid is not a valid UUID"}, status=400)

        chat = Chat.objects.filter(uuid=chat_uuid)
        if not chat.exists():
            return self.resp_chat_403
        chat = chat.first()
        if chat is None:
            return self.resp_chat_403
        if not chat.is_participant(request.user):
            return self.resp_chat_403

        partner = chat.get_partner(request.user)

        messages = chat.get_messages().filter(read=False, recipient=request.user)
        messages.update(read=True)

        from chat.consumers.messages import MessagesReadChat

        MessagesReadChat(
            user_id=str(request.user.uuid),  # all messages with receiver=user.uuid will be marked 'read'
            chat_id=str(chat.uuid),
        ).send(str(partner.uuid))

        return Response({"status": "ok"}, status=200)

    @extend_schema(request=SendMessageSerializer)
    @action(detail=False, methods=["post"])
    def send(self, request, chat_uuid=None):
        if not chat_uuid:
            return Response({"error": "chat_uuid is required"}, status=400)
        if not self._is_valid_uuid(chat_uuid):
            return Response({"error": "chat_uuid is not a valid UUID"}, status=400)

        # Use select_related to reduce database queries, but keep safe existence check
        chat = Chat.objects.select_related().filter(uuid=chat_uuid)
        if not chat.exists():
            return self.resp_chat_403
        chat = chat.first()
        if chat is None:
            return self.resp_chat_403

        if not chat.is_participant(request.user):
            return self.resp_chat_403

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        partner = chat.get_partner(request.user)
        message_text = serializer.validated_data.get("text", "")
        file = serializer.validated_data.get("file")

        try:
            message = create_and_deliver_message(
                chat=chat,
                sender=request.user,
                recipient=partner,
                text=message_text,
                file=file,
            )
        except MessageSendValidationError as exc:
            return Response({"error": exc.message}, status=400)
        except MatchSendForbidden:
            return self.resp_chat_403

        serialized_message = self.get_serializer(message).data

        if (
            settings.OPEN_CHAT_ENABLE_AUTOMATION_MESSAGE_REPLY_SUGGESTION
            and partner.email == settings.OPEN_CHAT_AUTOMATION_USER_EMAIL
            and User.objects.filter(email=settings.OPEN_CHAT_AUTOMATION_USER_EMAIL).exists()
        ):
            current_app.send_task(  # pyright: ignore[reportCallIssue]
                "management.tasks.open_chat_basic_chat_interaction",
                kwargs={
                    "chat_uuid": str(chat.uuid),
                    "message_uuid": str(message.uuid),
                    "sender_uuid": str(request.user.uuid),
                    "recipient_uuid": str(partner.uuid),
                    "user_message_text": message.text,
                },
            )

        if settings.OPEN_CHAT_ENABLE_AUTOMATION_MESSAGE_REPLY_SUGGESTION:
            # Create/reuse support-reply tasks for inbound messages to the partner
            # using the same idempotent helper as the Open Chat automation loop.
            from management import controller
            from open_chat.helpers import resolve_open_chat_automation_task_creator_user
            from open_chat.message_reply_suggestion import (
                create_or_reuse_support_reply_task_for_message,
            )

            if controller.is_base_management_user(partner):
                created_by_user = resolve_open_chat_automation_task_creator_user()
                if created_by_user is not None:
                    create_or_reuse_support_reply_task_for_message(
                        latest_message=message,
                        source_user=request.user,
                        target_user=partner,
                        created_by_user=created_by_user,
                        assigned_to_user=partner,
                        configuration_user_uuid=str(partner.uuid),
                        enqueue_interaction=True,
                    )

        return Response(serialized_message, status=200)

    # Keep the send_attachment method for backward compatibility
    @extend_schema(request=SendAttachmentSerializer)
    @action(detail=False, methods=["post"])
    def send_attachment(self, request, chat_uuid=None):
        # Convert the request to use the unified send method
        return self.send(request, chat_uuid)
