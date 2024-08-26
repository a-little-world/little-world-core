from django.db import models
from rest_framework import serializers
from .user import User
from uuid import uuid4


class SmsModel(models.Model):
    hash = models.UUIDField(default=uuid4, editable=False)

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sms_recipient")
    send_initator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sms_send_initator")

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    twilio_response = models.JSONField(default=dict)

    @classmethod
    def send_sms(cls, recipient, send_initator, message):
        sms = cls.objects.create(recipient=recipient, send_initator=send_initator, message=message)
        return sms


class SmsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsModel
        fields = "__all__"
