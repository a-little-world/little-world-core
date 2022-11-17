from django.db import models
from rest_framework import serializers
from .user import User


class Settings(models.Model):
    """ Stores the language code of the selected frontend language """
    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Key...

    language = models.CharField(max_length=20, default="en")

    # TODO: add a buch of settings for email notification preferences and co


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = '__all__'


class SelfSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = ["language"]
