from django.db import models
from rest_framework import serializers
from django.contrib.auth import get_user_model


class Profile(models.Model):
    """
    Default Profile model, fields:
    first_name: ...
    second_name: ...
    """
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE)  # Key...

    first_name = models.CharField(
        max_length=150,
        blank=False,
        default=None  # Will raise 'IntegrityError' if not passed
    )

    second_name = models.CharField(
        max_length=150,
        blank=False,
        default=None
    )


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = '__all__'
