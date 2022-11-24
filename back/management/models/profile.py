from django.db import models
from django.utils.translation import gettext_lazy as _, gettext_noop
from phonenumber_field.modelfields import PhoneNumberField
from back.utils import get_options_serializer
from datetime import datetime
from rest_framework import serializers
from multiselectfield import MultiSelectField
from back.utils import _double_uuid
from .user import User
from ..validators import (
    validate_availability,
    get_default_availability,
    validate_first_name,
    model_validate_first_name,
    model_validate_second_name,
    validate_postal_code,
    validate_second_name,
    DAYS,
    SLOTS
)
from django.utils.deconstruct import deconstructible
import sys
import os
#from back.utils import tt
from django.utils.translation import pgettext_lazy

# This can be used to handle changes in the api from the frontend
PROFILE_MODEL_VERSION = "1"


@deconstructible
class PathRename(object):

    def __init__(self, sub_path):
        self.path = sub_path

    def __call__(self, instance, filename):
        ext = filename.split('.')[-1]
        # Every profile image is stored as <usr-hash>.<random-hash>.ext
        # That way noone can brutefore user image paths, but we still know which user a path belongs to
        usr_hash = "-".join(instance.user.hash.split("-")[:3])
        filename = usr_hash + "." + str(_double_uuid()) + ".pimage." + ext
        path_new = os.path.join(self.path, filename)
        return path_new


class ProfileBase(models.Model):
    """
    Abstract base class for the default Profile Model
    Note: this represents the **current** profile
    this is not necessarily identical to the profile the user had when looking for his match!
    See the `ProfileAtMatchRequest` model for that
    """
    class Meta:
        # This is not a real-world model just a base class to use for a model
        # The real model is `Profile` below
        abstract = True

    version = models.CharField(default=PROFILE_MODEL_VERSION, max_length=255)

    """
    We like to always have that meta data!
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    """
    The first and second name of the user,
    these are the **only** fields marked with blank=False
    cause these are the **only** fields filled on profile creation,
    others are filled when the user filles the user_form
    """
    first_name = models.CharField(
        max_length=150,
        blank=False,
        default=None,  # Will raise 'IntegrityError' if not passed
        validators=[model_validate_first_name]
    )

    second_name = models.CharField(
        max_length=150,
        blank=False,
        default=None,
        validators=[model_validate_second_name]
    )

    birth_year = models.IntegerField(default=1984, blank=True)

    """
    A user can be either a volunteer or a language learner!
    But be aware that the user might change his choice
    e.g.: there might be a user that learns german and later decides he wants to volunteer
    therefore we store changes of this choice in `past_user_types`
    """
    class TypeChoices(models.IntegerChoices):
        VOLUNTEER = 0, _("Volunteer")
        LEARNER = 1, _("Language learner")
    user_type = models.IntegerField(
        choices=TypeChoices.choices, default=TypeChoices.VOLUNTEER)

    """
    This stores a dict of dates and what the users type was then
    a key and type is only added to this field if the user_type changes!
    """
    past_user_types = models.JSONField(blank=True, null=True)

    """
    Target group for matching
    Note: for volunteers this is a preference
    for learners this is which group they belong to
    """
    class TargetGroupChoices(models.IntegerChoices):
        # Allen Gruppen:
        ANY = 0, _("Any Group")
        # Geflüchteten (u.a. Ukraine, Jemen, Syrien):
        REFUGEES = 1, _("Refugees only")
        # Studierenden
        STUDENTS = 2, _("Students only")
        # Fachkräften aus dem Ausland:
        WORKERS = 3, _("Workers only")

    target_group = models.IntegerField(
        choices=TargetGroupChoices.choices, default=TargetGroupChoices.ANY)

    """
    Prefered partner sex
    """
    class ParterSexChoice(models.IntegerChoices):
        ANY = 0, _("Any sex")
        MALE = 1, _("Male only")
        FEMALE = 2, _("Female only")
    partner_sex = models.IntegerField(
        choices=ParterSexChoice.choices, default=ParterSexChoice.ANY)

    """
    Which medium the user preferes for
    """
    class SpeechMediumChoices(models.IntegerChoices):
        ANY = 0, _("Any medium")
        VIDEO = 1, _("Video only")
        PHONE = 2, _("Phone only")
    speech_medium = models.IntegerField(
        choices=SpeechMediumChoices.choices, default=SpeechMediumChoices.ANY)

    """
    where people want there match to be located
    """
    class ConversationPartlerLocation(models.IntegerChoices):
        ANYWHERE = 0, _("Location Anywhere")
        CLOSE = 1, _("Location close")
        FAR = 2, _("Location far")
    partner_location = models.IntegerField(
        choices=ConversationPartlerLocation.choices, default=ConversationPartlerLocation.ANYWHERE)

    """
    Postal code, char so we support international code for the future
    """
    postal_code = models.CharField(max_length=255, blank=True)

    class InterestChoices(models.IntegerChoices):
        SPORT = 0, pgettext_lazy("profile.sport-interest", "Sport")
        ART = 1, pgettext_lazy("profile.art-interest", "Art")
        MUSIC = 2, pgettext_lazy("profile.music-interest", "Music")
        LITERATURE = 3, pgettext_lazy(
            "profile.literature-interest", "Literature")
        VIDEO = 4, pgettext_lazy("profile.video-interest", "Video")
        FASHION = 5, pgettext_lazy("profile.fashion-interest", "Fashion")
        KULTURE = 6, pgettext_lazy("profile.culture-interest", "Culture")
        TRAVEL = 7, pgettext_lazy("profile.travel-interest", "Travel")
        FOOD = 8, pgettext_lazy("profile.food-interest", "Food")
        POLITICS = 9, pgettext_lazy("profile.politics-interest", "Politics")
        NATURE = 10, pgettext_lazy("profile.nature-interest", "Nature")
        SCIENCE = 11, pgettext_lazy("profile.science-interest", "Science")
        TECHNOLOGIE = 12, pgettext_lazy("profile.tech-interest", "Technology")
        HISTORY = 13, pgettext_lazy("profile.history-interest", "History")
        RELIGION = 14, pgettext_lazy("profile.religion-interest", "Religion")
        SOZIOLOGIE = 15, pgettext_lazy(
            "profile.soziologie-interest", "Sociology")
        FAMILY = 16, pgettext_lazy("profile.family-interest", "Family")
        PSYCOLOGY = 17, pgettext_lazy(
            "profile.psycology-interest", "Psycology")
        PERSON_DEV = 18, pgettext_lazy(
            "profile.pdev-interest", "Personal development")

    interests = MultiSelectField(
        choices=InterestChoices.choices, max_choices=20, max_length=20, blank=True)  # type: ignore

    additional_interests = models.TextField(default="", blank=True)

    """
    For simpliciy we store the time slots just in JSON
    Be aware of the validate_availability
    """
    availability = models.JSONField(
        null=True, blank=True, default=get_default_availability,
        validators=[validate_availability])  # type: ignore

    class LiabilityChoices(models.IntegerChoices):
        DECLINED = 0, _("Declined Liability")
        ACCEPTED = 1, _("Accepted Liability")
    liability = models.IntegerField(
        choices=LiabilityChoices.choices, default=LiabilityChoices.DECLINED)

    class NotificationChannelChoices(models.IntegerChoices):
        EMAIL = 0, _("Notify per email")
        SMS = 1, _("Notify per SMS")
        CALL = 2, _("Notify by calling")
    notify_channel = models.IntegerField(
        choices=NotificationChannelChoices.choices, default=NotificationChannelChoices.CALL)

    phone_mobile = PhoneNumberField(blank=True, unique=False)

    description = models.TextField(
        default="", blank=True, max_length=300)
    language_skill_description = models.TextField(
        default="", blank=True, max_length=300)

    class LanguageLevelChoices(models.IntegerChoices):
        A1 = 0, _("Level 0 (egal)")
        A2 = 1, _("Level 1 (B1 = (Alltagssituationen, Geschichten, Hoffnungen))")
        A3 = 2, _(
            "Level 2 (B2 = (fließende & spontane Gespräche, aktuelles Geschehen))")
        A4 = 3, _("Level 3 (C1 = (komplexe Themen, kaum nach Wörtern suchen))")
    lang_level = models.IntegerField(
        choices=LanguageLevelChoices.choices, default=LanguageLevelChoices.A1)

    # Profile image
    class ImageTypeChoice(models.IntegerChoices):
        AVATAR = 0, _("Avatar")
        IMAGE = 1, _("Image")

    profile_image_type = models.IntegerField(
        choices=ImageTypeChoice.choices, default=ImageTypeChoice.IMAGE)
    profile_image = models.ImageField(
        upload_to=PathRename("profile_pics/"), blank=True)
    profile_avatar_config = models.TextField(
        default="", blank=True)  # Contains the avatar builder config


class Profile(ProfileBase):

    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Key...


def _date_string():
    # TODO maybe we should add seconds since were using this in combination with unique together
    return datetime.now().strftime("%m/%d/%Y, %H:%M:%S")


class ProfileAtMatchRequest(ProfileBase):
    """
    This model is created everytime a users request a match
    It basicly stores a full copy of the profile when the user asks for a match
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE)  # TODO: do we really wan't to cascade here?
    # Sadly we cant use a date field here cause it is not json serializable
    # See https://stackoverflow.com/questions/11875770/how-to-overcome-datetime-datetime-not-json-serializable
    sdate = models.CharField(default=_date_string, max_length=255)

    # But we can add a read date time field without the unique contraint
    # This is convenient for e.g.: sorting in django admin
    date = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'sdate'], name='unique_user_sdate_combination'
            )
        ]


class ProfileSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    interests = serializers.MultipleChoiceField(
        choices=Profile.InterestChoices.choices)

    def get_options(self, obj):
        d = get_options_serializer(self, obj)
        # There is no way the serializer can determine the options for our availability
        # so lets just add it now, sice availability is stored as json anyways
        # we can easily change the choices here in the future
        if 'availability' in self.fields:
            d.update({  # Ourcourse there is no need to do this for the Censored profile view
                'availability': {day: SLOTS for day in DAYS}
            })
        return d

    class Meta:
        model = Profile
        fields = '__all__'


class SelfProfileSerializer(ProfileSerializer):
    class Meta:
        model = Profile
        fields = ['first_name', 'second_name', 'target_group', 'speech_medium',
                  'user_type', 'target_group', 'partner_sex', 'speech_medium',
                  'partner_location', 'postal_code', 'interests', 'availability',
                  'lang_level', 'additional_interests', 'language_skill_description', 'birth_year', 'description',
                  'notify_channel', 'phone_mobile', 'profile_image_type', 'profile_avatar_config', 'profile_image']

        extra_kwargs = dict(
            language_skill_description={
                "error_messages": {
                    'max_length': pgettext_lazy("profile.lskill-descr-to-long", "must have a maximum of 300 characters"),
                }
            },
            description={
                "error_messages": {
                    'max_length': pgettext_lazy("profile.descr-to-long", "must have a maximum of 300 characters"),
                }
            }
        )

    def validate_postal_code(self, value):
        return validate_postal_code(value)

    def validate_description(self, value):
        if len(value) < 10:  # TODO: higher?
            raise serializers.ValidationError(
                pgettext_lazy("profile.descr-to-short", "must have at least 10 characters"))
        return value


class CensoredProfileSerializer(SelfProfileSerializer):
    class Meta:
        model = Profile
        fields = ["first_name", 'interests', 'availability',
                  'notify_channel', 'phone_mobile', 'profile_image_type', 'profile_avatar_config', 'profile_image']
