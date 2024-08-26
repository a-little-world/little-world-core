from django.db import models
from rest_framework import serializers


class NewsLetterSubscription(models.Model):
    email = models.EmailField(null=False, blank=False, unique=True)
    two_step_verification = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)


class NewsletterSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsLetterSubscription
        fields = ["email", "two_step_verification", "created", "active"]
