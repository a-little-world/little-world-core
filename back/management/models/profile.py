from django.db import models
from django.utils.translation import gettext as _
from datetime import datetime
from rest_framework import serializers
from .user import User

# This can be used to handle changes in the api from the frontend
PROFILE_MODEL_VERSION = "1"


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
        default=None  # Will raise 'IntegrityError' if not passed
    )

    second_name = models.CharField(
        max_length=150,
        blank=False,
        default=None
    )

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
    # TODO: handle updating of this field
    past_user_types = models.JSONField(blank=True, null=True)

    """
    Target group for matching
    Note: for volunteers this is a preference
    for learners this is which group they belong to
    """
    class TargetGroupChoices(models.IntegerChoices):
        ANY = 0, _("Any Group")
        REFUGEES = 1, _("Refugees only")
        STUDENTS = 2, _("Students only")
        WORKERS = 3, _("Workers only")

    target_group = models.IntegerField(
        choices=TargetGroupChoices.choices, default=TargetGroupChoices.ANY)

    """
    Which medium the user preferes for  
    """
    class SpeechMediumChoices(models.IntegerChoices):
        ANY = 0, _("converstation_medium_any_trans")
        VIDEO = 1, _("converstation_medium_video_trans")
        PHONE = 2, _("converstation_medium_phone_trans")
    speech_medium = models.IntegerField(
        choices=SpeechMediumChoices.choices, default=SpeechMediumChoices.ANY)

    """
    For simpliciy we store the time slots just in JSON
    Be aware of the time_slot_serializer TODO
    """
    # TODO: create the time slot serializer
    availability = models.JSONField(null=True, blank=True)


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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    class Meta:
        model = Profile
        fields = '__all__'


class CensoredProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["first_name"]
