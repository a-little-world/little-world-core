from rest_framework import serializers, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from chat.models import ChatSerializer, Message, MessageSerializer, Chat
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from management.helpers import UserStaffRestricedModelViewsetMixin, DetailedPaginationMixin
from django.utils import timezone
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema
from emails import mails
from django.conf import settings
from management.tasks import send_email_background
from management.models.matches import Match
from chat.models import MessageAttachment


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100


class SendAttachmentSerializer(serializers.Serializer):
    file = serializers.FileField()
    text = serializers.CharField()


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField()


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
                qs = Chat.objects.get(Q(u1=self.request.user) | Q(u2=self.request.user), uuid=self.chat_uuid).get_messages().order_by("-created")
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

    @extend_schema(request=SendAttachmentSerializer)
    @action(detail=False, methods=["post"])
    def send_attachment(self, request, chat_uuid=None):
        if not chat_uuid:
            return Response({"error": "chat_uuid is required"}, status=400)

        chat = Chat.objects.filter(uuid=chat_uuid)
        if not chat.exists():
            return Response({"error": "(1) Chat doesn't exist or you have no permission to interact with it!"}, status=403)
        chat = chat.first()
        if not chat.is_participant(request.user):
            return Response({"error": "(2) You have no permission to interact with this chat!"}, status=403)

        serializer = SendAttachmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        partner = chat.get_partner(request.user)

        match = Match.get_match(request.user, partner)
        if not match.exists():
            return Response({"error": "(3) You are not matched with this user!"}, status=403)
        match = match.first()
        match.total_messages_counter += 1
        match.latest_interaction_at = timezone.now()
        match.save()

        latest_notified_message = Message.objects.filter(
            recipient=partner,
            recipient_notified=True,
        ).order_by("-created")

        def notify_recipient_email():
            if settings.USE_V2_EMAIL_APIS:
                send_email_background.delay("new-messages", user_id=partner.id)
            else:
                partner.send_email(
                    subject="Neue Nachricht(en) auf Little World",
                    mail_data=mails.get_mail_data_by_name("new_messages"),
                    mail_params=mails.NewUreadMessagesParams(
                        first_name=partner.profile.first_name,
                    ),
                )

        creation_time = timezone.now()
        recipiend_was_email_notified = False
        if latest_notified_message.exists():
            latest_notified_message = latest_notified_message.first()
            time_since_last_notif = (creation_time - latest_notified_message.created).total_seconds()
            if time_since_last_notif > 300:
                recipiend_was_email_notified = True
                notify_recipient_email()
        else:
            recipiend_was_email_notified = True
            notify_recipient_email()

        file = serializer.validated_data["file"]
        attachment = MessageAttachment.objects.create(file=file)

        message = Message.objects.create(chat=chat, sender=request.user, recipient=partner, recipient_notified=recipiend_was_email_notified, text=serializer.data["text"], attachments=attachment)

        serialized_message = self.serializer_class(message).data

        from chat.consumers.messages import NewMessage

        NewMessage(message=serialized_message, chat_id=chat.uuid, meta_chat_obj=ChatSerializer(chat, context={"user": partner}).data).send(partner.hash)
        return Response(serialized_message, status=200)

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
            # regardless of which chat!
            # sucht that the user doesn't get multiple emails in paralel
            # just cause he got messages in different chats
            recipient=partner,
            recipient_notified=True,
        ).order_by("-created")

        def notify_recipient_email():
            if settings.USE_V2_EMAIL_APIS:
                send_email_background.delay("new-messages", user_id=partner.id)
            else:
                partner.send_email(
                    subject="Neue Nachricht(en) auf Little World",
                    mail_data=mails.get_mail_data_by_name("new_messages"),
                    mail_params=mails.NewUreadMessagesParams(
                        first_name=partner.profile.first_name,
                    ),
                )

        # Now check if we should be sending out a new message notification
        # TODO: can this cause multiple emails due to concurrency?
        creation_time = timezone.now()
        recipiend_was_email_notified = False
        if latest_notified_message.exists():
            latest_notified_message = latest_notified_message.first()
            # Min 5 min delay between notifications!
            print("latest_notified_message", latest_notified_message)
            time_since_last_notif = (creation_time - latest_notified_message.created).total_seconds()
            print("time_since_last_notif", time_since_last_notif)

            if time_since_last_notif > 300:
                # ok then lets send the email
                # TODO: in future check if user is online and send push notification instead
                # TODO: ALSO for rate limiting there should probably be another checK:
                # for a maxium count of email notifications e.g.: within a day
                recipiend_was_email_notified = True
                notify_recipient_email()
        else:
            # No previous message was sent
            recipiend_was_email_notified = True
            notify_recipient_email()

        message = Message.objects.create(chat=chat, sender=request.user, recipient=partner, recipient_notified=recipiend_was_email_notified, text=serializer.data["text"])

        serialized_message = self.serializer_class(message).data

        from chat.consumers.messages import NewMessage

        NewMessage(message=serialized_message, chat_id=chat.uuid, meta_chat_obj=ChatSerializer(chat, context={"user": partner}).data).send(partner.hash)

        return Response(serialized_message, status=200)
