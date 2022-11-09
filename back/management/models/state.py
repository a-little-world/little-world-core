from django.db import models
from .user import User
from rest_framework import serializers


class State(models.Model):
    """
    This is the base state model for every user 
    It handles things like email verification, 
    the users matches, and if the userform is filled
    """

    # Key...
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # We love additional Information
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    """ Form page the user is currently on """
    user_form_page = models.IntegerField()

    """ If the user_form ist filled or not """
    user_form_state = models.IntegerField()


class StateSerializer(serializers.ModelSerializer):
    """
    Note: this serializer is not to be used for matches of the current user 
    This should only be used to expose data of the user to him self or an admin
    """
    class Meta:
        model = State
        fields = '__all__'
