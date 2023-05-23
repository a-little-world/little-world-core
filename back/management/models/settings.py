from django.db import models
from rest_framework import serializers
from .user import User
from multiselectfield import MultiSelectField
from uuid import uuid4


class UnsubscibeOptions(models.TextChoices):
    interview_requests = "interview_requests"

class EmailSettings(models.Model):
    
    hash = models.UUIDField(default=uuid4, editable=False)
    
    # email lists the user is currently unsubscribed from
    unsubscibed_options = MultiSelectField(
        choices=UnsubscibeOptions.choices, max_choices=20, max_length=500, default=[]
    )

def create_email_settings() -> EmailSettings:
    ems = EmailSettings.objects.create()
    return ems.id
    

class Settings(models.Model):
    """ Stores the language code of the selected frontend language """
    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Key...

    language = models.CharField(max_length=20, default="en")
    
    email_settings = models.OneToOneField(EmailSettings, on_delete=models.CASCADE, default=create_email_settings, unique=False)


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = '__all__'


class SelfSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = ["language"]
