from django.db import models
from management.models.management_tasks import MangementTask
from management.models.notifications import Notification
import uuid
import json
import base64
import zlib
from rest_framework import serializers
from back.utils import get_options_serializer
from back import utils
from multiselectfield import MultiSelectField
from management.models.question_deck import QuestionCardsDeck
from enum import Enum
from management.models.matches import Match
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from translations import get_translation


class State(models.Model):
    """
    This is the base state model for every user
    It handles things like email verification,
    the users matches, and if the userform is filled
    """

    # Key...
    user = models.OneToOneField("management.User", on_delete=models.CASCADE)

    question_card_deck = models.ForeignKey(QuestionCardsDeck, on_delete=models.SET_NULL, null=True, blank=True)

    # We love additional Information
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    """ Form page the user is currently on """
    user_form_page = models.IntegerField(default=0)

    class UserFormStateChoices(models.TextChoices):
        UNFILLED = "unfilled", _("Unfilled user form")
        FILLED = "filled", _("Filled user form")

    """ If the user_form ist filled or not """
    user_form_state = models.CharField(
        choices=UserFormStateChoices.choices,
        default=UserFormStateChoices.UNFILLED,
        max_length=255,
    )

    # Just some hash for verifying the email
    email_auth_hash = models.CharField(default=utils._double_uuid, max_length=255)
    email_auth_pin = models.IntegerField(
        # By wrapping in lambda this will get called when the model is created
        # and not at server start, then we get better randomization maybe
        # Also this conveniently inialized the pin
        default=utils._rand_int5
    )

    email_authenticated = models.BooleanField(default=False)

    still_active_reminder_send = models.BooleanField(default=False)
    still_active_reminder_confirmed = models.BooleanField(default=False)

    """
    For Tims experient of talking to all participants first 
    If this flag is set to 'True' Tim has to make an appointment with that user first.
    """
    require_pre_matching_call = models.BooleanField(default=False)
    had_prematching_call = models.BooleanField(default=False)

    """
    These are referense to the actual user model of this persons matches 
    """
    matches = models.ManyToManyField("management.User", related_name="+", blank=True)

    company = models.CharField(max_length=255, blank=True, null=True)

    class SearchingStateChoices(models.TextChoices):
        """
        All searching states!
        Idle is the default state at the beginning
        but we do (currently) automaticly set it to searching
        when the userform was finished.
        """

        IDLE = "idle", get_translation("models.state.searching_state.idle")
        SEARCHING = (
            "searching",
            get_translation("models.state.searching_state.searching"),
        )

    searching_state = models.CharField(
        choices=SearchingStateChoices.choices,
        default=SearchingStateChoices.IDLE,
        max_length=255,
    )
    searching_state_last_updated = models.DateTimeField(auto_now=timezone.now)
    prematch_booking_code = models.CharField(max_length=255, default=uuid.uuid4)

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
    notifications = models.ManyToManyField(Notification, related_name="n+", blank=True)

    class UserCategoryChoices(models.TextChoices):
        # For this we can use the default translations '_()'
        UNDEFINED = "undefined", _("Undefined")
        SPAM = "spam", _("Spam")
        LEGIT = "legit", _("Legit")
        TEST = "test", _("Test")

    user_category = models.CharField(
        choices=UserCategoryChoices.choices,
        default=UserCategoryChoices.UNDEFINED,
        max_length=255,
    )

    # Stores a users past emails ...
    past_emails = models.JSONField(blank=True, default=list)

    notes = models.TextField(blank=True, null=True)

    class ExtraUserPermissionChoices(models.TextChoices):
        API_SCHEMAS = "view-api-schema", _("Is allowed to view API schemas")
        DATABASE_SCHEMA = (
            "view-database-schema",
            _("Is allowed to view database schemas"),
        )
        AUTO_LOGIN = (
            "use-autologin-api",
            _("Is allowed to use the auto login api (with a specific token)"),
        )
        DOCS_VIEW = "view-docs", _("Is allowed to view the docs")
        EMAIL_TEMPLATES_VIEW = (
            "view-email-templates",
            _("Is allowed to view the email templates"),
        )
        STATS_VIEW = "view-stats", _("Is allowed to view the stats")

        MATCHING_USER = "matching-user", _("Is allowed to match users")
        UNCENSORED_ADMIN_MATCHER = (
            "uncensored-admin-matcher",
            _("Is allowed to match users without censorship"),
        )

    extra_user_permissions = MultiSelectField(
        max_length=8000,
        choices=ExtraUserPermissionChoices.choices,
        null=True,
        blank=True,
    )

    # This is basicly a list of all users that user manages
    managed_users = models.ManyToManyField("management.User", related_name="managed_users_by", blank=True)

    auto_login_api_token = models.CharField(default=utils._double_uuid, max_length=255)

    class TagChoices(models.TextChoices):
        SPAM = "state.tags-spam", "state.tags-spam"
        WRONG_LANG_LEVEL = (
            "state.tags-wrong-language-level",
            "state.tags-wrong-language-level",
        )
        NAME_NOT_CORRECT = "state.tags-name-not-correct", "state.tags-name-not-correct"
        DESCRIPTION_LANG_WRONG = (
            "state.tags-description-lang-wrong",
            "state.tags-description-lang-wrong",
        )
        LANGUAGE_LEVEL_TO_LOW_OR_UNCERTAIN = (
            "state.tags-language-level-to-low-or-uncertain",
            "state.tags-language-level-to-low-or-uncertain",
        )
        TOO_YUNG = "state.tags-too-young", "state.tags-too-young"
        DOESNT_AWNSER_MATCH = (
            "state.tags-doesnt-awnser-match",
            "state.tags-doesnt-awnser-match",
        )
        POSTAL_CODE_INVALID = (
            "state.tags-postal-code-invalid",
            "state.tags-postal-code-invalid",
        )
        WANTS_TO_LEARN_OTHER_LANGUAGE = (
            "state.tags-wants-to-learn-other-language",
            "state.tags-wants-to-learn-other-language",
        )
        REQUESTED_TO_BE_DELETED = (
            "state.tags-requested-to-be-deleted",
            "state.tags-requested-to-be-deleted",
        )
        UNCERTAIN_IF_VOL_OR_LEARNER = (
            "state.tags-uncertain-if-vol-or-learner",
            "state.tags-uncertain-if-vol-or-learner",
        )

    tags = MultiSelectField(
        choices=TagChoices.choices,
        max_choices=20,
        max_length=1000,
        blank=True,
        null=True,
    )  # type: ignore

    management_tasks = models.ManyToManyField(MangementTask, related_name="management_tasks", blank=True)

    # If the user is unresponsive this is a flag to exclue him from matching etc
    unresponsive = models.BooleanField(default=False)

    to_low_german_level = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Check if searching_state has changed
        if self.pk:  # Only for existing instances
            original = State.objects.get(pk=self.pk)
            if original.searching_state != self.searching_state:
                self.searching_state_last_updated = timezone.now()

        super().save(*args, **kwargs)

    def has_extra_user_permission(self, permission):
        if self.extra_user_permissions is None:
            return False

        return permission in self.extra_user_permissions

    def regnerate_email_auth_code(self, set_to_unauthenticated=True):
        # We do not log old auth codes, donsnt realy matter
        self.email_auth_hash = utils._double_uuid()
        self.email_auth_pin = utils._rand_int5()
        if set_to_unauthenticated:
            self.email_authenticated = False
        self.save()

    def change_searching_state(self, slug, trigger_score_update=True):
        # We put this list here so we ensure to stay safe if we add states that shouldn't be changed by the user!
        allowed_usr_change_search_states = ["idle", "searching"]
        assert slug in allowed_usr_change_search_states
        self.searching_state = slug
        self.save()
        
    def append_notes(self, message): 
        if(not (self.notes is None)):
            return self.notes + "\n{message}"
        else:
            return "\n{message}"

    def set_idle(self):
        self.searching_state = self.SearchingStateChoices.IDLE
        self.save()

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
            if m not in cur_unconfirmed:
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
        _check = _data["u"] == self.user.hash and _data["h"] == self.email_auth_hash and int(_data["p"]) == self.email_auth_pin
        if _check:
            self.email_authenticated = True
            self.save()
        return _check

    def get_email_auth_code_b64(self):
        return base64.urlsafe_b64encode(
            zlib.compress(
                bytes(
                    json.dumps(
                        {
                            "u": self.user.hash,
                            "h": self.email_auth_hash,
                            "p": self.email_auth_pin,
                        }
                    ),
                    "utf-8",
                )
            )
        ).decode()

    @classmethod
    def decode_email_auth_code_b64(cls, str_b64):
        return json.loads(zlib.decompress(base64.urlsafe_b64decode(str_b64.encode())).decode())


@receiver(post_save, sender=State)
def populate_parents(sender, instance, created, **kwargs):
    if created:
        instance.question_card_deck = QuestionCardsDeck.objects.create(user=instance.user)
        instance.save()


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
        fields = "__all__"


class FrontendStatusEnum(Enum):
    user_form_incomplete = "user_form_incomplete"
    pre_matching = "pre_matching"
    searching_no_match = "searching_no_match"
    matched = "matched"
    matched_searching = "matched_searching"


class FrontendStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = []

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        # TODO: some state for user has open poposals?

        if instance.user_form_state == State.UserFormStateChoices.UNFILLED:
            rep["status"] = FrontendStatusEnum.user_form_incomplete.value
            return rep
        elif instance.require_pre_matching_call and (not instance.had_prematching_call):
            rep["status"] = FrontendStatusEnum.pre_matching.value
            return rep

        # Now check if the user is matched
        has_atleast_one_match = (
            Match.objects.filter(
                Q(user1=instance.user) | Q(user2=instance.user),
                support_matching=False,
            ).count()
            > 0
        )

        if has_atleast_one_match:
            if instance.searching_state == State.SearchingStateChoices.IDLE:
                rep["status"] = FrontendStatusEnum.matched.value
                return rep
            elif instance.searching_state == State.SearchingStateChoices.SEARCHING:
                rep["status"] = FrontendStatusEnum.matched_searching.value
                return rep
        else:
            rep["status"] = FrontendStatusEnum.searching_no_match.value
        return rep


class SelfStateSerializer(StateSerializer):
    class Meta:
        model = State
        fields = [
            "user_form_state",
            "user_form_page",
            "unconfirmed_matches_stack",
            "searching_state",
            # "email_authenticated"
            # TODO A-- will be imporant once we allow to verify the email later
        ]
