from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from emails import mails
from management.helpers import DetailedPaginationMixin, UserStaffRestricedModelViewsetMixin
from management.models.matches import Match
from management.tasks import send_email_background
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from chat.models import Chat, ChatSerializer, Message, MessageAttachment, MessageSerializer


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

    def filter_queryset(self, queryset):
        print("FILTERING")
        if hasattr(self, "chat_uuid"):
            if self.request.user.is_staff:
                qs = Chat.objects.get(uuid=self.chat_uuid).get_messages().order_by("-created")
                return qs
            else:
                qs = (
                    Chat.objects.get(Q(u1=self.request.user) | Q(u2=self.request.user), uuid=self.chat_uuid)
                    .get_messages()
                    .order_by("-created")
                )
                return qs
        return super().filter_queryset(queryset)

    def list(self, request, *args, **kwargs):
        if "chat_uuid" in kwargs:
            self.chat_uuid = kwargs["chat_uuid"]
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        return Message.objects.filter(chat__in=Chat.get_chats(self.request.user)).order_by("-created")

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
        return Response(self.serializer_class(obj).data, status=200)

    @extend_schema(request=SendMessageSerializer)
    @action(detail=False, methods=["post"])
    def chat_read(self, request, chat_uuid=None):
        if not chat_uuid:
            return Response({"error": "chat_uuid is required"}, status=400)

        chat = Chat.objects.filter(uuid=chat_uuid)
        if not chat.exists():
            return self.resp_chat_403
        chat = chat.first()
        if not chat.is_participant(request.user):
            return self.resp_chat_403

        partner = chat.get_partner(request.user)

        messages = chat.get_messages().filter(read=False, recipient=request.user)
        messages.update(read=True)

        from chat.consumers.messages import MessagesReadChat

        MessagesReadChat(
            user_id=request.user.hash,  # all messages with receiver=user.hash will be marked 'read'
            chat_id=chat.uuid,
        ).send(partner.hash)

        return Response({"status": "ok"}, status=200)

    @extend_schema(request=SendMessageSerializer)
    @action(detail=False, methods=["post"])
    def send(self, request, chat_uuid=None):
        if not chat_uuid:
            return Response({"error": "chat_uuid is required"}, status=400)

        chat = Chat.objects.filter(uuid=chat_uuid)
        if not chat.exists():
            return self.resp_chat_403
        chat = chat.first()
        if not chat.is_participant(request.user):
            return self.resp_chat_403

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        partner = chat.get_partner(request.user)

        # Check if the users are still matched, otherwise no new messages can be send
        match = Match.get_match(request.user, partner)
        if not match.exists():
            return self.resp_chat_403
        match = match.first()

        match.total_messages_counter += 1
        match.latest_interaction_at = timezone.now()
        match.save()

        # retrieve the newest message the recipient was notified about
        latest_notified_message = Message.objects.filter(
            recipient=partner,
            recipient_notified=True,
        ).order_by("-created")

        def notify_recipient_email():
            send_email_background.delay("new-messages", user_id=partner.id)

        # Now check if we should be sending out a new message notification
        creation_time = timezone.now()
        recipiend_was_email_notified = False
        if latest_notified_message.exists():
            latest_notified_message = latest_notified_message.first()
            # Min 5 min delay between notifications!
            time_since_last_notif = (creation_time - latest_notified_message.created).total_seconds()

            if time_since_last_notif > 300:
                recipiend_was_email_notified = True
                notify_recipient_email()
        else:
            recipiend_was_email_notified = True
            notify_recipient_email()

        # Process attachment if present
        attachment = None
        attachment_widget = ""
        if 'file' in serializer.validated_data and serializer.validated_data['file']:
            file = serializer.validated_data['file']
            attachment = MessageAttachment.objects.create(file=file)
            
            file_title = file.name
            file_ending = file.name.split(".")[-1]
            is_image = file_ending.lower() in ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "ico", "webp"]
            attachment_link = attachment.file.url
            
            def get_attachment_widget(is_image, attachment_link):
                if is_image:
                    return f'<AttachmentWidget {{"attachmentTitle": "Image", "attachmentLink": null, "imageSrc": "{attachment_link}"}} ></AttachmentWidget>'
                else:
                    return f'<AttachmentWidget {{"attachmentTitle": "{file_title}", "attachmentLink": "{attachment_link}", "imageSrc": null}} ></AttachmentWidget>'
            
            attachment_widget = get_attachment_widget(is_image, attachment_link)

        # Combine text and attachment if both are present
        message_text = ""
        if 'text' in serializer.validated_data and serializer.validated_data['text']:
            message_text = serializer.validated_data['text']
        
        if attachment_widget:
            if message_text:
                message_text = f"{attachment_widget}\n{message_text}"
            else:
                message_text = attachment_widget

        # Create message with combined content
        message = Message.objects.create(
            chat=chat,
            sender=request.user,
            recipient=partner,
            recipient_notified=recipiend_was_email_notified,
            text=message_text,
            attachments=attachment,
            parsable_message=bool(attachment_widget),
        )

        serialized_message = self.serializer_class(message).data

        from chat.consumers.messages import NewMessage

        NewMessage(
            message=serialized_message,
            chat_id=chat.uuid,
            meta_chat_obj=ChatSerializer(chat, context={"user": partner}).data,
        ).send(partner.hash)

        return Response(serialized_message, status=200)

    # Keep the send_attachment method for backward compatibility
    @extend_schema(request=SendAttachmentSerializer)
    @action(detail=False, methods=["post"])
    def send_attachment(self, request, chat_uuid=None):
        # Convert the request to use the unified send method
        return self.send(request, chat_uuid)
