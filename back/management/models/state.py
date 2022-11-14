from django.db import models
from .user import User
import json
import base64
import zlib
from back import utils
import random
from datetime import datetime
from django.utils.translation import gettext_lazy as _
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
    user_form_page = models.IntegerField(default=0)

    class UserFormStateChoices(models.IntegerChoices):
        UNFILLED = 0, _("Unfilled user form")
        FILLED = 1, _("Filled user form")

    """ If the user_form ist filled or not """
    user_form_state = models.IntegerField(
        default=UserFormStateChoices.UNFILLED)

    # Just some hash for verifying the email
    email_auth_hash = models.CharField(
        default=utils._double_uuid, max_length=255)
    email_auth_pin = models.IntegerField(
        # By wrapping in lambda this will get called when the model is created
        # and not at server start, then we get better randomization maybe
        # Also this conveniently inialized the pin
        default=utils._rand_int6)

    email_authenticated = models.BooleanField(default=False)

    matches = models.ManyToManyField(User, related_name='+')

    """
    This state is used to sendout the unread email notification for you have new messages
    """
    unread_message_count = models.IntegerField(default=0)
    unread_message_count_update_time = models.DateTimeField(
        default=datetime.now)

    def is_email_verified(self):
        return self.email_authenticated

    def check_email_auth_pin(self, pin):
        """
        checks email verification pin, this shall only be used it the user is logged in!
        """
        _check = pin == self.email_auth_pin
        if _check:
            self.email_authenticated = True
            self.save()
        return _check

    def check_email_auth_code_b64(self, code):
        """
        checks the email verification credentials
        note this is will be used it authentication through a link ( with out being logged in )
        """
        _data = self.decode_email_auth_code_b64(code)
        # u: user hash, h: email verification hash, p: email verification pin
        _check = _data["u"] == self.user.hash and \
            _data["h"] == self.email_auth_hash and \
            int(_data["p"]) == self.email_auth_pin
        if _check:
            self.email_authenticated = True
            self.save()
        return _check

    def get_email_auth_code_b64(self):
        return base64.urlsafe_b64encode(zlib.compress(bytes(json.dumps({
            "u": self.user.hash, "h": self.email_auth_hash, "p": self.email_auth_pin}), 'utf-8'))).decode()

    @classmethod
    def decode_email_auth_code_b64(cls, str_b64):
        return json.loads(zlib.decompress(
            base64.urlsafe_b64decode(str_b64.encode())).decode())


class StateSerializer(serializers.ModelSerializer):
    """
    Note: this serializer is not to be used for matches of the current user
    This should only be used to expose data of the user to him self or an admin
    """
    usr_hash = serializers.SerializerMethodField()

    def get_usr_hash(self, obj):
        return obj.user.hash

    class Meta:
        model = State
        fields = '__all__'


class SelfStateSerializer(StateSerializer):

    class Meta:
        model = State
        fields = ["user_form_state", "user_form_page", "usr_hash"]
