from django.db import models
from .user import User
import json
import base64
import zlib
import random
from datetime import datetime
from django.utils.translation import pgettext_lazy, gettext_lazy as _
from rest_framework import serializers
from .notifications import Notification
from back.utils import get_options_serializer
from back import utils
from multiselectfield import MultiSelectField


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

    class UserFormStateChoices(models.TextChoices):
        UNFILLED = "unfilled", _("Unfilled user form")
        FILLED = "filled", _("Filled user form")

    """ If the user_form ist filled or not """
    user_form_state = models.CharField(choices=UserFormStateChoices.choices,
                                       default=UserFormStateChoices.UNFILLED,
                                       max_length=255)

    # Just some hash for verifying the email
    email_auth_hash = models.CharField(
        default=utils._double_uuid, max_length=255)
    email_auth_pin = models.IntegerField(
        # By wrapping in lambda this will get called when the model is created
        # and not at server start, then we get better randomization maybe
        # Also this conveniently inialized the pin
        default=utils._rand_int5)

    email_authenticated = models.BooleanField(default=False)

    """
    These are referense to the actual user model of this persons matches 
    """
    matches = models.ManyToManyField(User, related_name='+', blank=True)

    class MatchingStateChoices(models.TextChoices):
        """
        All matching states! 
        Idle is the default state at the beginning
        but we do (currently) automaticly set it to searching 
        when the userform was finished.
        """
        IDLE = "idle", pgettext_lazy(
            "models.state.matching-state-idle",
            "Not Searching (Idle)")
        SEARCHING = "searching", pgettext_lazy(
            "models.state.matching-state-searching",
            "Searching")

    matching_state = models.CharField(choices=MatchingStateChoices.choices,
                                      default=MatchingStateChoices.IDLE,
                                      max_length=255)

    """
    This contains a list of matches the user has not yet confirmed 
    this can be used by the frontend to display them as 'new'
    POST api/user/confrim_match/
    data = [<usr-hash>, ... ] 
    """
    unconfirmed_matches_stack = models.JSONField(default=list, blank=True)

    """
    all user notification
    reference to models.notifications.Notification
    """
    notifications = models.ManyToManyField(
        Notification, related_name='n+', blank=True)

    """
    This state is used to sendout the unread email notification
    when a user has new messages on the plattform
    """
    # TODO: the unread message count must be reset from in the chat!
    unread_chat_message_count = models.IntegerField(default=0)
    unread_chat_message_count_update_time = models.DateTimeField(
        default=datetime.now)

    class UserCategoryChoices(models.TextChoices):
        # For this we can use the default translations '_()'
        UNDEFINED = "undefined", _("Undefined")
        SPAM = "spam", _("Spam")
        LEGIT = "legit", _("Legit")
        TEST = "test", _("Test")
    user_category = models.CharField(
        choices=UserCategoryChoices.choices,
        default=UserCategoryChoices.UNDEFINED,
        max_length=255)

    # Stores a users past emails ...
    past_emails = models.JSONField(blank=True, default=list)

    class ExtraUserPermissionChoices(models.TextChoices):
        API_SCHEMAS = "view-api-schema", _("Is allowed to view API schemas")
        DATABASE_SCHEMA = "view-database-schema", _(
            "Is allowed to view database schemas")
        AUTO_LOGIN = "use-autologin-api", _(
            "Is allowed to use the auto login api (with a specific token)")

    extra_user_permissions = MultiSelectField(
        max_length=1000,
        choices=ExtraUserPermissionChoices.choices,
        null=True, blank=True)

    auto_login_api_token = models.CharField(
        default=utils._double_uuid, max_length=255)

    class TagChoices(models.TextChoices):
        SPAM = "state.tags-spam"
        WRONG_LANG_LEVEL = "state.tags-wrong-language-level"
        NAME_NOT_CORRECT = "state.tags-name-not-correct"
        DESCRIPTION_LANG_WRONG = "state.tags-description-lang-wrong"
        LANGUAGE_LEVEL_TO_LOW_OR_UNCERTAIN = "state.tags-language-level-to-low-or-uncertain"
        TOO_YUNG = "state.tags-too-young"
        DOESNT_AWNSER_MATCH = "state.tags-doesnt-awnser-match"
        POSTAL_CODE_INVALID = "state.tags-postal-code-invalid"
        WANTS_TO_LEARN_OTHER_LANGUAGE = "state.tags-wants-to-learn-other-language"
        REQUESTED_TO_BE_DELETED = "state.tags-requested-to-be-deleted"
        UNCERTAIN_IF_VOL_OR_LEARNER = "state.tags-uncertain-if-vol-or-learner"

    tags = MultiSelectField(
        choices=TagChoices.choices, max_choices=20,
        max_length=1000, blank=True, null=True)  # type: ignore

    def has_extra_user_permission(self, permission):
        return permission in self.extra_user_permissions

    def regnerate_email_auth_code(self, set_to_unauthenticated=True):
        # We do not log old auth codes, donsnt realy matter
        self.email_auth_hash = utils._double_uuid()
        self.email_auth_pin = utils._rand_int5()
        self.email_authenticated = set_to_unauthenticated
        self.save()

    def change_searching_state(self, slug, trigger_score_update=True):
        # We put this list here so we ensure to stay safe if we add states that shouldn't be changed by the user!
        allowed_usr_change_search_states = ['idle', 'searching']
        assert slug in allowed_usr_change_search_states
        self.matching_state = slug
        self.save()

        if trigger_score_update and slug == 'searching':
            print("Triggering score update")
            from ..tasks import calculate_directional_matching_score_background
            calculate_directional_matching_score_background.delay(
                self.user.hash)

    def archive_email_adress(self, email):
        self.past_emails.append(email)
        self.save()

    def set_user_form_completed(self):
        self.user_form_state = self.UserFormStateChoices.FILLED
        self.save()

    def confirm_matches(self, matches: list):
        """
        Confirms some matches, basicly by removing them from the stack 
        *but* this can throw 'Not and unconfirmed match'
        """
        cur_unconfirmed = self.unconfirmed_matches_stack
        for m in matches:
            if not m in cur_unconfirmed:
                raise Exception("Not an unconfirmed match {m}".format(m=m))
            else:
                cur_unconfirmed.remove(m)
        self.unconfirmed_matches_stack = cur_unconfirmed
        self.save()

    def is_email_verified(self):
        return self.email_authenticated

    def is_user_form_filled(self):
        return self.user_form_state == self.UserFormStateChoices.FILLED

    def get_email_auth_pin(self):
        return self.email_auth_pin

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
    options = serializers.SerializerMethodField()

    def get_options(self, obj):
        return get_options_serializer(self, obj)

    class Meta:
        model = State
        fields = '__all__'


class SelfStateSerializer(StateSerializer):

    class Meta:
        model = State
        fields = [
            "user_form_state",
            "user_form_page",
            "unconfirmed_matches_stack",
            "matching_state"
            # "email_authenticated"
            # TODO A-- will be imporant once we allow to verify the email later
        ]
