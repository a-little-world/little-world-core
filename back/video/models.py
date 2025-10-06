from uuid import uuid4

from django.db import models
from django.db.models import Q
from management.models.profile import CensoredProfileSerializer
from rest_framework.serializers import ModelSerializer
from rest_framework import serializers


class LiveKitRoom(models.Model):
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    u1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u1_livekit_room")
    u2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u2_livekit_room")

    @classmethod
    def get_room(cls, user1, user2):
        return cls.objects.get(Q(u1=user1, u2=user2) | Q(u1=user2, u2=user1))


class LivekitWebhookEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    data = models.JSONField()


class LivekitSession(models.Model):
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    room = models.ForeignKey(
        "video.LiveKitRoom", on_delete=models.CASCADE, related_name="livekit_session", null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    # a session is created when a user first joins a specific room
    # a session is 'stopped' when both participants have left the room
    is_active = models.BooleanField(default=True)

    u1_active = models.BooleanField(default=False)
    u2_active = models.BooleanField(default=False)

    u1_was_active = models.BooleanField(default=False)
    u2_was_active = models.BooleanField(default=False)

    both_have_been_active = models.BooleanField(default=False)
    
    unusual_length = models.BooleanField(default=False)
    start_end_before_correction = models.TextField(null=True, blank=True)

    u1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u1_livekit_session")
    u2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u2_livekit_session")

    first_active_user = models.ForeignKey(
        "management.User", on_delete=models.CASCADE, related_name="first_active_user", null=True, blank=True
    )

    webhook_events = models.ManyToManyField("video.LivekitWebhookEvent", related_name="livekit_session")


class SerializeLivekitSession(ModelSerializer):
    room_uuid = serializers.CharField(source='room.uuid', read_only=True, allow_null=True)
    
    class Meta:
        model = LivekitSession
        fields = ["uuid", "created_at", "room_uuid"]

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        rep["activeUsers"] = []

        if instance.u1_active:
            rep["activeUsers"].append(instance.u1.hash)
        if instance.u2_active:
            rep["activeUsers"].append(instance.u2.hash)

        user = None
        if "user" in self.context:
            user = self.context["user"]
        elif "request" in self.context:
            user = self.context["request"].user

        if user:
            if user == instance.u1:
                rep["partner"] = CensoredProfileSerializer(instance.u2.profile).data
                rep["partner"]["id"] = instance.u2.hash
            else:
                rep["partner"] = CensoredProfileSerializer(instance.u1.profile).data
                rep["partner"]["id"] = instance.u1.hash

        return rep
