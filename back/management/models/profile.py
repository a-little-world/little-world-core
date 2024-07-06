from django.db import models
from django.utils.encoding import force_str
from phonenumber_field.modelfields import PhoneNumberField
from back.utils import get_options_serializer
from datetime import datetime
from rest_framework import serializers
from multiselectfield import MultiSelectField
from back.utils import _double_uuid
from django.core.files import File
from management.validators import (
    validate_availability,
    get_default_availability,
    model_validate_first_name,
    model_validate_second_name,
    validate_postal_code,
    DAYS,
    SLOTS,
    SLOT_TRANS,
)
from django.utils.deconstruct import deconstructible
import os
from translations import get_translation

# This can be used to handle changes in the api from the frontend
PROFILE_MODEL_VERSION = "1"


def base_lang_skill():
    return [{"lang": "german", "level": "level-0"}]


@deconstructible
class PathRename(object):
    def __init__(self, sub_path):
        self.path = sub_path

    def __call__(self, instance, filename):
        ext = filename.split(".")[-1]
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
        validators=[model_validate_first_name],
    )

    second_name = models.CharField(
        max_length=150,
        blank=False,
        default=None,
        validators=[model_validate_second_name],
    )

    birth_year = models.IntegerField(default=1984, blank=True)

    """
    A user can be either a volunteer or a language learner!
    But be aware that the user might change his choice
    e.g.: there might be a user that learns german and later decides he wants to volunteer
    therefore we store changes of this choice in `past_user_types`
    """

    class TypeChoices(models.TextChoices):
        LEARNER = "learner", get_translation("profile.user_type.learner")
        VOLUNTEER = "volunteer", get_translation("profile.user_type.volunteer")

    user_type = models.CharField(
        choices=TypeChoices.choices, default=TypeChoices.LEARNER, max_length=255
    )

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

    class TargetGroupChoices2(models.TextChoices):
        ANY = "any", get_translation("profile.target_group.any")
        REFUGEE = "refugee", get_translation("profile.target_group.refugee")
        STUDENT = "student", get_translation("profile.target_group.student")
        WORKER = "worker", get_translation("profile.target_group.worker")

    target_group = models.CharField(
        choices=TargetGroupChoices2.choices,
        default=TargetGroupChoices2.ANY,
        max_length=255,
    )

    target_groups = MultiSelectField(
        choices=TargetGroupChoices2.choices, max_choices=20, max_length=1000, blank=True
    )  # type: ignore

    # DEPRICATED!!! replaced with 'partner_gender'
    class ParterSexChoice(models.TextChoices):
        ANY = "any", get_translation("profile.partner_sex.any")
        MALE = "male", get_translation("profile.partner_sex.male")
        FEMALE = "female", get_translation("profile.partner_sex.female")

    # DEPRICATED!!! replaced with 'partner_gender'
    partner_sex = models.CharField(
        choices=ParterSexChoice.choices, default=ParterSexChoice.ANY, max_length=255
    )

    class PartnerGenderChoices(models.TextChoices):
        ANY = "any", get_translation("profile.partner_gender.any")
        MALE = "male", get_translation("profile.partner_gender.male")
        FEMALE = "female", get_translation("profile.partner_gender.female")

    class GenderChoices(models.TextChoices):
        ANY = "any", get_translation("profile.gender.any")
        MALE = "male", get_translation("profile.gender.male")
        FEMALE = "female", get_translation("profile.gender.female")

    gender = models.CharField(
        choices=GenderChoices.choices, default=None, null=True, max_length=255
    )

    partner_gender = models.CharField(
        choices=PartnerGenderChoices.choices,
        default=PartnerGenderChoices.ANY,
        max_length=255,
    )

    """
    Which medium the user preferes for
    """
    class SpeechMediumChoices(models.TextChoices):
        ANY_VOL = "any.vol", get_translation("profile.speech_medium.any_vol")
        ANY_LER = "any.ler", get_translation("profile.speech_medium.any_ler")
        VIDEO_VOL = "video.vol", get_translation("profile.speech_medium.video_vol")
        VIDEO_LER = "video.ler", get_translation("profile.speech_medium.video_ler")
        PHONE_VOL = "phone.vol", get_translation("profile.speech_medium.phone_vol")
        PHONE_LER = "phone.ler", get_translation("profile.speech_medium.phone_ler")

    class SpeechMediumChoices2(models.TextChoices):
        ANY = "any", get_translation("profile.speech_medium.any")
        VIDEO = "video", get_translation("profile.speech_medium.video")
        PHONE = "phone", get_translation("profile.speech_medium.phone")

    speech_medium = models.CharField(
        choices=SpeechMediumChoices2.choices,
        default=SpeechMediumChoices2.ANY,
        max_length=255,
    )

    """
    where people want there match to be located
    WE ARE CURRENTLY NOT ASKING THIS!
    """

    class ConversationPartlerLocation2(models.TextChoices):
        ANYWHERE = (
            "anywhere",
            get_translation("profile.partner_location.anywhere"),
        )
        CLOSE = "close", get_translation("profile.partner_location.close")
        FAR = "far", get_translation("profile.partner_location.far")

    partner_location = models.CharField(
        choices=ConversationPartlerLocation2.choices,
        default=ConversationPartlerLocation2.ANYWHERE,
        max_length=255,
    )

    newsletter_subscribed = models.BooleanField(default=False)

    """
    Postal code, char so we support international code for the future
    """
    postal_code = models.CharField(max_length=255, blank=True)

    class InterestChoices(models.TextChoices):
        SPORT = "sport", get_translation("profile.interest.sport")
        ART = "art", get_translation("profile.interest.art")
        MUSIC = "music", get_translation("profile.interest.music")
        LITERATURE = "literature", get_translation("profile.interest.literature")
        VIDEO = "video", get_translation("profile.interest.video")
        FASHION = "fashion", get_translation("profile.interest.fashion")
        KULTURE = "culture", get_translation("profile.interest.culture")
        TRAVEL = "travel", get_translation("profile.interest.travel")
        FOOD = "food", get_translation("profile.interest.food")
        POLITICS = "politics", get_translation("profile.interest.politics")
        NATURE = "nature", get_translation("profile.interest.nature")
        SCIENCE = "science", get_translation("profile.interest.science")
        TECHNOLOGIE = "technology", get_translation("profile.interest.technology")
        HISTORY = "history", get_translation("profile.interest.history")
        RELIGION = "religion", get_translation("profile.interest.religion")
        SOZIOLOGIE = "sociology", get_translation("profile.interest.sociology")
        FAMILY = "family", get_translation("profile.interest.family")
        PSYCOLOGY = "psycology", get_translation("profile.interest.pychology")
        PERSON_DEV = (
            "personal-development",
            get_translation("profile.interest.personal_development"),
        )

    interests = MultiSelectField(
        choices=InterestChoices.choices, max_choices=20, max_length=1000, blank=True
    )  # type: ignore

    additional_interests = models.TextField(default="", blank=True, max_length=300)

    """
    For simpliciy we store the time slots just in JSON
    Be aware of the validate_availability
    """
    availability = models.JSONField(
        null=True,
        blank=True,
        default=get_default_availability,
        validators=[validate_availability],
    )  # type: ignore

    class LiabilityChoices(models.TextChoices):
        DECLINED = "declined", get_translation("profile.liability.declined")
        ACCEPTED = "accepted", get_translation("profile.liability.accepted")

    liability = models.CharField(
        choices=LiabilityChoices.choices,
        default=LiabilityChoices.DECLINED,
        max_length=255,
    )

    class NotificationChannelChoices(models.TextChoices):
        EMAIL = "email", get_translation("profile.notification_channel.email")
        SMS = "sms", get_translation("profile.notification_channel.sms")

    notify_channel = models.CharField(
        choices=NotificationChannelChoices.choices,
        default=NotificationChannelChoices.EMAIL,
        max_length=255,
    )

    phone_mobile = PhoneNumberField(blank=True, unique=False)

    other_target_group = models.CharField(max_length=255, blank=True)

    description = models.TextField(default="", blank=True, max_length=999)
    language_skill_description = models.TextField(
        default="", blank=True, max_length=300
    )

    class MinLangLevelPartnerChoices(models.TextChoices):
        LEVEL_0 = "level-0", get_translation("profile.min_lang_level_partner.level_0")
        LEVEL_1 = "level-1", get_translation("profile.min_lang_level_partner.level_1")
        LEVEL_2 = "level-2", get_translation("profile.min_lang_level_partner.level_2")
        LEVEL_3 = "level-3", get_translation("profile.min_lang_level_partner.level_3")

    min_lang_level_partner = models.CharField(
        choices=MinLangLevelPartnerChoices.choices,
        default=MinLangLevelPartnerChoices.LEVEL_0,
        max_length=255,
    )

    class LanguageChoices(models.TextChoices):
        ENGLISH = "english", get_translation("profile.lang.english")
        GERMAN = "german", get_translation("profile.lang.german")
        SPANISH = "spanish", get_translation("profile.lang.spanish")
        FRENCH = "french", get_translation("profile.lang.french")
        ITALIAN = "italian", get_translation("profile.lang.italian")
        DUTCH = "dutch", get_translation("profile.lang.dutch")
        PORTUGUESE = "portuguese", get_translation("profile.lang.portuguese")
        RUSSIAN = "russian", get_translation("profile.lang.russian")
        CHINESE = "chinese", get_translation("profile.lang.chinese")
        JAPANESE = "japanese", get_translation("profile.lang.japanese")
        KOREAN = "korean", get_translation("profile.lang.korean")
        ARABIC = "arabic", get_translation("profile.lang.arabic")
        TURKISH = "turkish", get_translation("profile.lang.turkish")
        SWEDISH = "swedish", get_translation("profile.lang.swedish")
        POLISH = "polish", get_translation("profile.lang.polish")
        DANISH = "danish", get_translation("profile.lang.danish")
        NORWEGIAN = "norwegian", get_translation("profile.lang.norwegian")
        FINNISH = "finnish", get_translation("profile.lang.finnish")
        GREEK = "greek", get_translation("profile.lang.greek")
        CZECH = "czech", get_translation("profile.lang.czech")
        HUNGARIAN = "hungarian", get_translation("profile.lang.hungarian")
        ROMANIAN = "romanian", get_translation("profile.lang.romanian")
        INDONESIAN = "indonesian", get_translation("profile.lang.indonesian")
        HEBREW = "hebrew", get_translation("profile.lang.hebrew")
        THAI = "thai", get_translation("profile.lang.thai")
        VIETNAMESE = "vietnamese", get_translation("profile.lang.vietnamese")
        UKRAINIAN = "ukrainian", get_translation("profile.lang.ukrainian")
        SLOVAK = "slovak", get_translation("profile.lang.slovak")
        CROATIAN = "croatian", get_translation("profile.lang.croatian")
        SERBIAN = "serbian", get_translation("profile.lang.serbian")
        BULGARIAN = "bulgarian", get_translation("profile.lang.bulgarian")
        LITHUANIAN = "lithuanian", get_translation("profile.lang.lithuanian")
        LATVIAN = "latvian", get_translation("profile.lang.latvian")
        ESTONIAN = "estonian", get_translation("profile.lang.estonian")
        PERSIAN = "persian", get_translation("profile.lang.persian")
        AFRIKAANS = "afrikaans", get_translation("profile.lang.afrikaans")
        SWAHILI = "swahili", get_translation("profile.lang.swahili")

    class LanguageSkillChoices(models.TextChoices):
        LEVEL_0 = "level-0", get_translation("profile.lang_level.level_0")
        LEVEL_1 = "level-1", get_translation("profile.lang_level.level_1")
        LEVEL_2 = "level-2", get_translation("profile.lang_level.level_2")
        LEVEL_3 = "level-3", get_translation("profile.lang_level.level_3")
        LEVEL_NATIVE_VOL = (
            "level-4",
            get_translation("profile.lang_level.level_4_native.vol"),
        )

    lang_skill = models.JSONField(default=base_lang_skill)

    class ImageTypeChoice(models.TextChoices):
        AVATAR = "avatar", get_translation("profile.image_type.avatar")
        IMAGE = "image", get_translation("profile.image_type.image")

    image_type = models.CharField(
        choices=ImageTypeChoice.choices, default=ImageTypeChoice.IMAGE, max_length=255
    )
    image = models.ImageField(upload_to=PathRename("profile_pics/"), blank=True)
    avatar_config = models.JSONField(
        default=dict, blank=True
    )  # Contains the avatar builder config

    display_language = models.CharField(
        choices=[
            ("de", get_translation("profile.display_language.de")),
            ("en", get_translation("profile.display_language.en")),
        ],
        default="de",
        max_length=255,
    )

    gender_prediction = models.JSONField(null=True, blank=True)

    liability_accepted = models.BooleanField(default=False)

    def add_profile_picture_from_local_path(self, path):
        print("Trying to add the pic", path)
        self.image.save(os.path.basename(path), File(open(path, "rb")))
        self.save()

    def check_form_completion(
        self,
        mark_completed=True,
        set_searching_if_completed=True,
        trigger_score_calulation=True,
    ):
        """
           Checks if the userform is completed
        TODO this could be a little more consize and extract better on which user form page
        the user is currently
        """
        fields_required_for_completion = [
            "description",  # This is required but 'language_skill_description' is not!
            "image"
            if self.image_type == self.ImageTypeChoice.IMAGE
            else "avatar_config",
            "target_group",
            *(
                ["phone_mobile"]
                if self.notify_channel  # phone is only required if notification channel is not email ( so it's sms or phone )
                != self.NotificationChannelChoices.EMAIL
                else []
            ),
        ]
        msgs = []
        is_completed = True
        for field in fields_required_for_completion:
            value = getattr(self, field)
            if value == "":  # TODO: we should also run the serializer
                msgs.append(
                    get_translation("profile.completion_check.missing_value").format(
                        val=field
                    )
                )
                is_completed = False

        if is_completed and mark_completed:
            self.user.state.set_user_form_completed()

        if is_completed and set_searching_if_completed:
            self.user.state.change_searching_state(
                slug="searching", trigger_score_update=trigger_score_calulation
            )

        return is_completed, msgs

    def save(self, *args, **kwargs):
        super(ProfileBase, self).save(*args, **kwargs)


class Profile(ProfileBase):
    user = models.OneToOneField("management.User", on_delete=models.CASCADE)  # Key...


def _date_string():
    # TODO maybe we should add seconds since we're using this in combination with unique together
    return datetime.now().strftime("%m/%d/%Y, %H:%M:%S")


class ProfileAtMatchRequest(ProfileBase):
    """
    This model is created every time a user requests a match
    It basically stores a full copy of the profile when the user asks for a match
    """

    usr_hash = models.CharField(max_length=255, unique=False, blank=True, null=True)
    # Sadly we can't use a date field here because it is not JSON serializable
    # See https://stackoverflow.com/questions/11875770/how-to-overcome-datetime-datetime-not-json-serializable
    sdate = models.CharField(default=_date_string, max_length=255)

    # But we can add a read date time field without the unique constraint
    # This is convenient for e.g., sorting in django admin
    date = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usr_hash", "date"], name="unique_user_sdate_combination"
            )
        ]


class ProfileSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    interests = serializers.MultipleChoiceField(choices=Profile.InterestChoices.choices)
    target_groups = serializers.MultipleChoiceField(choices=Profile.TargetGroupChoices2.choices)
    image = serializers.ImageField(
        max_length=None, allow_empty_file=True, allow_null=True, required=False
    )

    def get_options(self, obj):
        d = get_options_serializer(self, obj)
        # There is no way the serializer can determine the options for our availability
        # so let's just add it now, since availability is stored as JSON anyways
        # we can easily change the choices here in the future

        if (
            "availability" in self.Meta.fields
        ):  # <- TODO: does this check work with inheritance?
            d.update(
                {  # Our course there is no need to do this for the Censored profile view
                    "availability": {
                        day: [
                            {"value": slot, "tag": SLOT_TRANS[slot]} for slot in SLOTS
                        ]
                        for day in DAYS
                    }
                }
            )

        if "lang_skill" in self.Meta.fields:
            d.update(
                {
                    "lang_skill": {
                        "level": [
                            {"value": l0, "tag": force_str(l1, strings_only=True)}
                            for l0, l1 in Profile.LanguageSkillChoices.choices
                        ],
                        "lang": [
                            {"value": l0, "tag": force_str(l1, strings_only=True)}
                            for l0, l1 in Profile.LanguageChoices.choices
                        ],
                    }
                }
            )

        # TODO: we might want to update the options for the language skill choices also
        return d

    class Meta:
        model = Profile
        fields = "__all__"


class SelfProfileSerializer(ProfileSerializer):
    class Meta:
        model = Profile
        fields = [
            "first_name",
            "second_name",
            "target_group",
            "speech_medium",
            "user_type",
            "target_group",
            "speech_medium",
            "partner_location",
            "postal_code",
            "interests",
            "availability",
            "min_lang_level_partner",
            "additional_interests",
            "language_skill_description",
            "birth_year",
            "description",
            "notify_channel",
            "phone_mobile",
            "image_type",
            "avatar_config",
            "image",
            "lang_skill",
            "gender",
            "partner_gender",
            "liability_accepted",
            "display_language",
            "other_target_group",
            "target_groups",
            "newsletter_subscribed",
        ]

        extra_kwargs = dict(
            language_skill_description={
                "error_messages": {
                    "max_length": get_translation("profile.lskill_descr_too_long"),
                }
            },
            description={
                "error_messages": {
                    "max_length": get_translation("profile.descr_too_long"),
                }
            },
        )

    def validate(self, data):
        """
        Additional model validation for the profile
        this is especially important for the image vs. avatar!
        """
        if "image_type" in data:
            if data["image_type"] == Profile.ImageTypeChoice.IMAGE:

                def __no_img():
                    raise serializers.ValidationError(
                        {"image": get_translation("profile.image_missing")}
                    )

                if not "image" in data:
                    if not self.instance.image:
                        # If the image is not present we only proceed if there is already an image set
                        __no_img()
                elif data["image"] is None:
                    # Only allow removing the image if then the avatar config is set
                    if not "image_type" in data or not (
                        data["image_type"] == Profile.ImageTypeChoice.AVATAR
                    ):
                        raise serializers.ValidationError(
                            {
                                "image": get_translation(
                                    "profile.image_removal_without_avatar"
                                )
                            }
                        )
                elif not data["image"]:
                    __no_img()
            if data["image_type"] == Profile.ImageTypeChoice.AVATAR:
                if not "avatar_config" in data or not data["avatar_config"]:
                    raise serializers.ValidationError(
                        {"avatar_config": get_translation("profile.avatar_missing")}
                    )
        return data

    def validate_liability_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                get_translation("profile.liability_declined")
            )
        return value

    def validate_postal_code(self, value):
        return validate_postal_code(value)

    def validate_interests(self, value):
        if len(value) < 3:
            raise serializers.ValidationError(
                get_translation("profile.interests.min_number")
            )
        return value
    
    def validate_target_groups(self, value):
        if len(value) < 1:
            raise serializers.ValidationError(
                get_translation("profile.target_groups.min_number")
            )
        return value

    def validate_lang_skill(self, value):
        german_level_present = False
        language_count_map = {}
        for lang in value:
            if "german" in lang["lang"]:
                german_level_present = True
            if not (lang["level"] in Profile.LanguageSkillChoices.values):
                raise serializers.ValidationError(
                    get_translation("profile.lang_level_invalid")
                )

            if not (lang["lang"] in Profile.LanguageChoices.values):
                raise serializers.ValidationError(
                    get_translation("profile.lang_invalid")
                )

            if not lang["lang"] in language_count_map:
                language_count_map[lang["lang"]] = 1
            else:
                language_count_map[lang["lang"]] += 1

        if not all([v <= 1 for v in language_count_map.values()]):
            raise serializers.ValidationError(get_translation("profile.lang_duplicate"))

        if not german_level_present:
            raise serializers.ValidationError(
                get_translation("profile.lang_de_missing")
            )
        return value

    def validate_description(self, value):
        if len(value) < 10:  # TODO: higher?
            raise serializers.ValidationError(
                get_translation("profile.descr_too_short")
            )
        return value


class CensoredProfileSerializer(SelfProfileSerializer):
    class Meta:
        model = Profile
        fields = [
            "first_name",
            "interests",
            "availability",
            "notify_channel",
            "phone_mobile",
            "image_type",
            "lang_skill",
            "avatar_config",
            "image",
            "description",
            "additional_interests",
            "language_skill_description",
            "user_type",
        ]


class MinimalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            "first_name",
            "second_name",
            "image_type",
            "avatar_config",
            "image",
            "description",
            "user_type",
        ]


class ProposalProfileSerializer(SelfProfileSerializer):
    class Meta:
        model = Profile
        fields = [
            "first_name",
            "availability",
            "image_type",
            "avatar_config",
            "image",
            "description",
        ]
