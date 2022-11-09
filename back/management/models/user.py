from django.db import models
from uuid import uuid4
from rest_framework import serializers
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    The default django user model.
    It is recommended to extend this class
    make small modifications if required
    in the settings we set this via 'AUTH_USER_MODEL'
    """
    hash = models.CharField(max_length=100, blank=True,
                            unique=True, default=uuid4)  # type: ignore


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


class CensoredUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["hash"]
