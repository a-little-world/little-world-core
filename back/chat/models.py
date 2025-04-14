from uuid import uuid4

from django.core.paginator import Paginator
from django.db import models
from django.db.models import Max, Q, Case, When, Value, IntegerField
from management import models as management_models
from rest_framework import serializers


class Chat(models.Model):
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

    u1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u1")
    u2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u2")

    created = models.DateTimeField(auto_now_add=True)

    def get_partner(self, user):
        return self.u1 if self.u2 == user else self.u2

    def is_participant(self, user):
        return self.u1 == user or self.u2 == user

    @classmethod
    def get_chats(cls, user):
        is_matching_user = user.state.has_extra_user_permission(
            management_models.state.State.ExtraUserPermissionChoices.MATCHING_USER
        )
        queryset = Chat.objects.filter(Q(u1=user) | Q(u2=user))
        
        if is_matching_user:
            queryset = queryset.annotate(
                newest_message_time=Max("message__created"),
                has_messages=Case(
                    When(newest_message_time__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField()
                )
            ).order_by("-has_messages", "-newest_message_time", "-created")
        else:
            queryset = queryset.annotate(
                newest_message_time=Max("message__created")
            ).filter(
                newest_message_time__isnull=False
            ).order_by("-newest_message_time")
        
        return queryset

    def get_messages(self):
        return Message.objects.filter(chat=self).order_by("-created")

    @classmethod
    def get_chat(cls, users):
        chat = Chat.objects.filter(u1__in=users, u2__in=users).order_by("-created")
        if chat.exists():
            return chat.first()
        return None

    def get_unread_count(self, user):
        return self.get_messages().filter(read=False, recipient=user).count()

    def get_newest_message(self):
        return self.get_messages().order_by("-created").first()

    @classmethod
    def get_or_create_chat(cls, user1, user2):
        chat = cls.objects.filter(Q(u1=user1, u2=user2) | Q(u1=user2, u2=user1))
        if chat.exists():
            return chat.first()
        else:
            return cls.objects.create(u1=user1, u2=user2)

    def get_past_messages_openai(self, message_depth):
        return OpenAiChatSerializer(self, message_depth=message_depth).data


class ChatInModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ["uuid"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["id"] = instance.uuid
        del representation["uuid"]

        representation["unread_count"] = instance.get_unread_count(self.context["user"])
        representation["newest_message"] = MessageSerializer(instance.get_newest_message()).data

        return representation


class ChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ["uuid", "u1", "u2", "created"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        if ("request" in self.context) or ("user" in self.context):
            # We need to check if the users are still matched otherwise we censor the parter profile
            user = self.context["request"].user if "request" in self.context else self.context["user"]
            partner = instance.get_partner(user)

            if management_models.matches.Match.get_match(user, partner).exists():
                profile = management_models.profile.CensoredProfileSerializer(partner.profile).data
                representation["partner"] = profile
                representation["partner"]["id"] = partner.hash
            else:
                representation["partner"] = {"censored": True, "id": "censored"}
                representation["is_unmatched"] = True

            del representation["u1"]
            del representation["u2"]

            representation["unread_count"] = instance.get_unread_count(user)
            representation["newest_message"] = MessageSerializer(instance.get_newest_message()).data
        else:
            representation["u1"] = instance.u1.hash
            representation["u2"] = instance.u2.hash

        return representation


class MessageAttachment(models.Model):
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    file = models.FileField(upload_to="message_attachments")

    def save(self, *args, **kwargs):
        file_ending = self.file.name.split(".")[-1]
        self.file.name = str(self.uuid) + "." + file_ending
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.uuid)


class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

    sender = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="message_sender")
    recipient = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="message_recipient")

    recipient_notified = models.BooleanField(default=False)

    text = models.TextField()
    parsable_message = models.BooleanField(default=False)

    read = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)
    attachments = models.ForeignKey(MessageAttachment, on_delete=models.CASCADE, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["sender", "recipient"]),
            models.Index(fields=["recipient", "sender"]),
            models.Index(fields=["created"]),
            models.Index(fields=["recipient", "created"]),
            models.Index(fields=["sender", "created"]),
        ]


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["uuid", "sender", "created", "text", "read"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["sender"] = instance.sender.hash

        from management.models.state import State

        sender_staff = instance.sender.is_staff or instance.sender.state.has_extra_user_permission(
            State.ExtraUserPermissionChoices.MATCHING_USER
        )

        if sender_staff or instance.parsable_message:
            representation["parsable"] = True

        censor_text = self.context.get("censor_text", False)
        if censor_text:
            representation["text"] = "Message censored"

        return representation


class OpenAiMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["uuid"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        representation["role"] = "assistant" if instance.sender.automated else "user"
        representation["content"] = instance.text
        del representation["uuid"]

        return representation


class OpenAiChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ["uuid", "u1", "u2", "created"]

    def __init__(self, *args, message_depth=5, **kwargs):
        super().__init__(*args, **kwargs)
        self.message_depth = message_depth

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        messages = instance.get_messages()
        representation["messages"] = OpenAiMessageSerializer(
            Paginator(messages, self.message_depth).page(1), many=True
        ).data


class ChatSessions(models.Model):
    user = models.ForeignKey("management.User", on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()


class ChatConnections(models.Model):
    user = models.ForeignKey("management.User", on_delete=models.CASCADE)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)
    time_created = models.DateTimeField(auto_now_add=True)

    @classmethod
    def is_user_online(cls, user):
        return cls.objects.filter(user=user, is_online=True).exists()
