from django.db import models
from django.utils.encoding import force_str
from django.utils.translation import gettext_lazy as _, gettext_noop
from phonenumber_field.modelfields import PhoneNumberField
from django.utils import translation
from phonenumber_field.phonenumber import PhoneNumber
from back.utils import get_options_serializer
from datetime import datetime
from rest_framework import serializers
from multiselectfield import MultiSelectField
from back.utils import _double_uuid
from django.core.files import File
from management.validators import (
    validate_availability,
    get_default_availability,
    validate_first_name,
    model_validate_first_name,
    model_validate_second_name,
    validate_postal_code,
    validate_second_name,
    DAYS,
    SLOTS,
    SLOT_TRANS
)
from django.utils.deconstruct import deconstructible
import sys
import os
#from back.utils import tt
from django.utils.translation import pgettext_lazy

# This can be used to handle changes in the api from the frontend
PROFILE_MODEL_VERSION = "1"


def base_lang_skill():
    return [{'lang': 'german', 'level': 'level-0.vol'}]


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
    class TypeChoices(models.TextChoices):
        LEARNER = "learner", pgettext_lazy(
            "profile.user-type.learner", "Language learner")
        VOLUNTEER = "volunteer", pgettext_lazy(
            "profile.user-type.volunteer", "Volunteer")

    user_type = models.CharField(
        choices=TypeChoices.choices,
        default=TypeChoices.LEARNER,
        max_length=255)

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
    class TargetGroupChoices(models.TextChoices):

        ANY_VOL = "any.vol", pgettext_lazy(
            "profile.target-group.any-vol", "other")

        ANY_LER = "any.ler", pgettext_lazy(
            "profile.target-group.any-ler", "other")

        REFUGEE_VOL = "refugee.vol", pgettext_lazy(
            "profile.target-group.refugee-vol", "Refugees")

        REFUGEE_LER = "refugee.ler", pgettext_lazy(
            "profile.target-group.refugee-ler", "Refugees")

        STUDENT_VOL = "student.vol", pgettext_lazy(
            "profile.target-group.student-vol", "Students")

        STUDENT_LER = "student.ler", pgettext_lazy(
            "profile.target-group.student-ler", "Students")

        WORKER_VOL = "worker.vol", pgettext_lazy(
            "profile.target-group.worker-vol", "Workers")

        WORKER_LER = "worker.ler", pgettext_lazy(
            "profile.target-group.worker-ler", "Workers")

    target_group = models.CharField(
        choices=TargetGroupChoices.choices,
        default=TargetGroupChoices.ANY_VOL,
        max_length=255)
    
    target_groups = MultiSelectField(
        choices=TargetGroupChoices.choices, max_choices=20,
        max_length=1000, blank=True)  # type: ignore

    # DEPRICATED!!! replaced with 'partner_gender'
    class ParterSexChoice(models.TextChoices):
        ANY = "any", pgettext_lazy("profile.partner-sex.any", "Any")
        MALE = "male", pgettext_lazy("profile.partner-sex.male", "Male only")
        FEMALE = "female", pgettext_lazy(
            "profile.partner-sex.female", "Female only")

    # DEPRICATED!!! replaced with 'partner_gender'
    partner_sex = models.CharField(
        choices=ParterSexChoice.choices,
        default=ParterSexChoice.ANY,
        max_length=255)

    class PartnerGenderChoices(models.TextChoices):
        ANY = "any", pgettext_lazy("profile.partner-gender.any", "Any")
        MALE = "male", pgettext_lazy(
            "profile.partner-gender.male", "Male only")
        FEMALE = "female", pgettext_lazy(
            "profile.partner-gender.female", "Female only")

    class GenderChoices(models.TextChoices):
        ANY = "any", pgettext_lazy("profile.gender.any", "Don't want to say")
        MALE = "male", pgettext_lazy("profile.gender.male", "Male")
        FEMALE = "female", pgettext_lazy(
            "profile.gender.female", "Female")

    gender = models.CharField(
        choices=GenderChoices.choices,
        default=GenderChoices.ANY,
        max_length=255)

    partner_gender = models.CharField(
        choices=PartnerGenderChoices.choices,
        default=PartnerGenderChoices.ANY,
        max_length=255)

    """
    Which medium the user preferes for
    """
    class SpeechMediumChoices(models.TextChoices):
        ANY_VOL = "any.vol", pgettext_lazy(
            "profile.speech-medium.any-vol", "Any")

        ANY_LER = "any.ler", pgettext_lazy(
            "profile.speech-medium.any-ler", "Any")

        VIDEO_VOL = "video.vol", pgettext_lazy(
            "profile.speech-medium.video-vol", "Video only")

        VIDEO_LER = "video.ler", pgettext_lazy(
            "profile.speech-medium.video-ler", "Video only")

        PHONE_VOL = "phone.vol", pgettext_lazy(
            "profile.speech-medium.phone-vol", "Phone only")

        PHONE_LER = "phone.ler", pgettext_lazy(
            "profile.speech-medium.phone-ler", "Phone only")

    speech_medium = models.CharField(
        choices=SpeechMediumChoices.choices,
        default=SpeechMediumChoices.ANY_VOL,
        max_length=255)

    """
    where people want there match to be located
    WE ARE CURRENTLY NOT ASKING THIS!
    """
    class ConversationPartlerLocation(models.TextChoices):
        ANYWHERE_VOL = "anywhere.vol", pgettext_lazy(
            "profile.partner-location.anywhere-vol", "Anywhere")

        ANYWHERE_LER = "anywhere.ler", pgettext_lazy(
            "profile.partner-location.anywhere-ler", "Anywhere")

        CLOSE_VOL = "close.vol", pgettext_lazy(
            "profile.partner-location.close-vol", "Close")

        CLOSE_LER = "close.ler", pgettext_lazy(
            "profile.partner-location.close-ler", "Close")

        FAR_VOL = "far.vol", pgettext_lazy(
            "profile.partner-location.far-vol", "Far")

        FAR_LER = "far.ler", pgettext_lazy(
            "profile.partner-location.far-ler", "Far")

    partner_location = models.CharField(
        choices=ConversationPartlerLocation.choices,
        default=ConversationPartlerLocation.ANYWHERE_VOL,
        max_length=255)

    newsletter_subscribed = models.BooleanField(default=False)

    """
    Postal code, char so we support international code for the future
    """
    postal_code = models.CharField(max_length=255, blank=True)

    class InterestChoices(models.TextChoices):
        SPORT = "sport", pgettext_lazy("profile.sport-interest", "Sport")
        ART = "art", pgettext_lazy("profile.art-interest", "Art")
        MUSIC = "music", pgettext_lazy("profile.music-interest", "Music")
        LITERATURE = "literature", pgettext_lazy(
            "profile.literature-interest", "Literature")
        VIDEO = "video", pgettext_lazy("profile.video-interest", "Video")
        FASHION = "fashion", pgettext_lazy(
            "profile.fashion-interest", "Fashion")
        KULTURE = "culture", pgettext_lazy(
            "profile.culture-interest", "Culture")
        TRAVEL = "travel", pgettext_lazy("profile.travel-interest", "Travel")
        FOOD = "food", pgettext_lazy("profile.food-interest", "Food")
        POLITICS = "politics", pgettext_lazy(
            "profile.politics-interest", "Politics")
        NATURE = "nature", pgettext_lazy("profile.nature-interest", "Nature")
        SCIENCE = "science", pgettext_lazy(
            "profile.science-interest", "Science")
        TECHNOLOGIE = "technology", pgettext_lazy(
            "profile.tech-interest", "Technology")
        HISTORY = "history", pgettext_lazy(
            "profile.history-interest", "History")
        RELIGION = "religion", pgettext_lazy(
            "profile.religion-interest", "Religion")
        SOZIOLOGIE = "sociology", pgettext_lazy(
            "profile.soziologie-interest", "Sociology")
        FAMILY = "family", pgettext_lazy("profile.family-interest", "Family")
        PSYCOLOGY = "psycology", pgettext_lazy(
            "profile.psycology-interest", "Psychology")
        PERSON_DEV = "personal-development", pgettext_lazy(
            "profile.pdev-interest", "Personal development")

    interests = MultiSelectField(
        choices=InterestChoices.choices, max_choices=20,
        max_length=1000, blank=True)  # type: ignore

    additional_interests = models.TextField(
        default="", blank=True, max_length=300)

    """
    For simpliciy we store the time slots just in JSON
    Be aware of the validate_availability
    """
    availability = models.JSONField(
        null=True, blank=True, default=get_default_availability,
        validators=[validate_availability])  # type: ignore

    class LiabilityChoices(models.TextChoices):
        DECLINED = "declined", pgettext_lazy(
            "profile.liability.declined", "Declined Liability")

        ACCEPTED = "accepted", pgettext_lazy(
            "profile.liability.accepted", "Accepted Liability")

    liability = models.CharField(
        choices=LiabilityChoices.choices,
        default=LiabilityChoices.DECLINED,
        max_length=255)

    class NotificationChannelChoices(models.TextChoices):
        EMAIL = "email", pgettext_lazy(
            "profile.notify-channel.email", "to be notified by e-mail only.")
        SMS = "sms", pgettext_lazy(
            "profile.notify-channel.sms", "to be notified by e-mail & SMS.")

    notify_channel = models.CharField(
        choices=NotificationChannelChoices.choices,
        default=NotificationChannelChoices.EMAIL,
        max_length=255)

    phone_mobile = PhoneNumberField(blank=True, unique=False)
    
    other_target_group = models.CharField(max_length=255, blank=True)

    description = models.TextField(
        default="", blank=True, max_length=999)
    language_skill_description = models.TextField(
        default="", blank=True, max_length=300)

    # TODO: depricated!!!
    class LanguageLevelChoices(models.TextChoices):
        """
        For all choices we allow to version a version for a volunteer 
        and a version for a lanaguage learer
        NOTE: this means we *need* to update selection if a users switches from learner to volunteer or vice versa
        """
        LEVEL_0_VOL = "level-0.vol", pgettext_lazy(
            "profile.lang-level.level-0-vol", "any")

        LEVEL_0_LER = "level-0.ler", pgettext_lazy(
            "profile.lang-level.level-0-ler", "any")

        LEVEL_1_VOL = "level-1.vol", pgettext_lazy(
            "profile.lang-level.level-1-vol", "B1 = (everyday situations, stories, hopes)")

        LEVEL_1_LER = "level-1.ler", pgettext_lazy(
            "profile.lang-level.level-1-ler", "B1 = (everyday situations, stories, hopes)")

        LEVEL_2_VOL = "level-2.vol", pgettext_lazy(
            "profile.lang-level.level-2-vol", "B2 = (fluent & spontaneous conversations, current events)")

        LEVEL_2_LER = "level-2.ler", pgettext_lazy(
            "profile.lang-level.level-2-ler", "B2 = (fluent & spontaneous conversations, current events)")

        LEVEL_3_VOL = "level-3.vol", pgettext_lazy(
            "profile.lang-level.level-3-vol", "C1/C2 = (complex topics, hardly searching for words)")

        LEVEL_3_LER = "level-3.ler", pgettext_lazy(
            "profile.lang-level.level-3-ler", "C1/C2 = (complex topics, hardly searching for words)")
        
    class MinLangLevelPartnerChoices(models.TextChoices):
        LEVEL_0 = "level-0", pgettext_lazy(
            "profile.lang-level.level-0", "A1 & A2 (beginner level)")

        LEVEL_1 = "level-1", pgettext_lazy(
            "profile.lang-level.level-1", "B1 (everyday situations, stories)")

        LEVEL_2 = "level-2", pgettext_lazy(
            "profile.lang-level.level-2", "B2 (fluent & spontaneous conversations)")

        LEVEL_3 = "level-3", pgettext_lazy(
            "profile.lang-level.level-3", "C1/C2 (complex topics)")

    min_lang_level_partner = models.CharField(
        choices=MinLangLevelPartnerChoices.choices,
        default=MinLangLevelPartnerChoices.LEVEL_0,
        max_length=255)

    # TODO: depricated!!!
    lang_level = models.CharField(
        choices=LanguageLevelChoices.choices,
        default=LanguageLevelChoices.LEVEL_0_VOL,
        max_length=255)

    class LanguageChoices(models.TextChoices):
        ENGLISH = "english", pgettext_lazy("profile.lang.english", "English")
        GERMAN = "german", pgettext_lazy("profile.lang.german", "German")
        SPANISH = "spanish", pgettext_lazy("profile.lang.spanish", "Spanish")
        FRENCH = "french", pgettext_lazy("profile.lang.french", "French")
        ITALIAN = "italian", pgettext_lazy("profile.lang.italian", "Italian")
        DUTCH = "dutch", pgettext_lazy("profile.lang.dutch", "Dutch")
        PORTUGUESE = "portuguese", pgettext_lazy(
            "profile.lang.portuguese", "Portuguese")
        RUSSIAN = "russian", pgettext_lazy("profile.lang.russian", "Russian")
        CHINESE = "chinese", pgettext_lazy("profile.lang.chinese", "Chinese")
        JAPANESE = "japanese", pgettext_lazy(
            "profile.lang.japanese", "Japanese")
        KOREAN = "korean", pgettext_lazy("profile.lang.korean", "Korean")
        ARABIC = "arabic", pgettext_lazy("profile.lang.arabic", "Arabic")
        TURKISH = "turkish", pgettext_lazy("profile.lang.turkish", "Turkish")
        SWEDISH = "swedish", pgettext_lazy("profile.lang.swedish", "Swedish")
        POLISH = "polish", pgettext_lazy("profile.lang.polish", "Polish")
        DANISH = "danish", pgettext_lazy("profile.lang.danish", "Danish")
        NORWEGIAN = "norwegian", pgettext_lazy(
            "profile.lang.norwegian", "Norwegian")
        FINNISH = "finnish", pgettext_lazy("profile.lang.finnish", "Finnish")
        GREEK = "greek", pgettext_lazy("profile.lang.greek", "Greek")
        CZECH = "czech", pgettext_lazy("profile.lang.czech", "Czech")
        HUNGARIAN = "hungarian", pgettext_lazy(
            "profile.lang.hungarian", "Hungarian")
        ROMANIAN = "romanian", pgettext_lazy(
            "profile.lang.romanian", "Romanian")
        INDONESIAN = "indonesian", pgettext_lazy(
            "profile.lang.indonesian", "Indonesian")
        HEBREW = "hebrew", pgettext_lazy("profile.lang.hebrew", "Hebrew")
        THAI = "thai", pgettext_lazy("profile.lang.thai", "Thai")
        VIETNAMESE = "vietnamese", pgettext_lazy(
            "profile.lang.vietnamese", "Vietnamese")
        UKRAINIAN = "ukrainian", pgettext_lazy(
            "profile.lang.ukrainian", "Ukrainian")
        SLOVAK = "slovak", pgettext_lazy("profile.lang.slovak", "Slovak")
        CROATIAN = "croatian", pgettext_lazy(
            "profile.lang.croatian", "Croatian")
        SERBIAN = "serbian", pgettext_lazy("profile.lang.serbian", "Serbian")
        BULGARIAN = "bulgarian", pgettext_lazy(
            "profile.lang.bulgarian", "Bulgarian")
        LITHUANIAN = "lithuanian", pgettext_lazy(
            "profile.lang.lithuanian", "Lithuanian")
        LATVIAN = "latvian", pgettext_lazy("profile.lang.latvian", "Latvian")
        ESTONIAN = "estonian", pgettext_lazy(
            "profile.lang.estonian", "Estonian")
        PERSIAN = "persian", pgettext_lazy("profile.lang.persian", "Persian")
        AFRIKAANS = "afrikaans", pgettext_lazy(
            "profile.lang.afrikaans", "Afrikaans")
        SWAHILI = "swahili", pgettext_lazy("profile.lang.swahili", "Swahili")

    class LanguageSkillChoices(models.TextChoices):
        LEVEL_0 = "level-0", pgettext_lazy(
            "profile.lang-level.level-0", "A1 & A2 (beginner level)")

        LEVEL_1 = "level-1", pgettext_lazy(
            "profile.lang-level.level-1", "B1 (everyday situations, stories)")

        LEVEL_2 = "level-2", pgettext_lazy(
            "profile.lang-level.level-2", "B2 (fluent & spontaneous conversations)")

        LEVEL_3 = "level-3", pgettext_lazy(
            "profile.lang-level.level-3", "C1/C2 (complex topics)")

    lang_skill = models.JSONField(default=base_lang_skill)
    
    class ImageTypeChoice(models.TextChoices):
        AVATAR = "avatar", pgettext_lazy("profile.image-type.avatar", "Avatar")
        IMAGE = "image", pgettext_lazy("profile.image-type.image", "Image")

    image_type = models.CharField(
        choices=ImageTypeChoice.choices,
        default=ImageTypeChoice.IMAGE,
        max_length=255)
    image = models.ImageField(
        upload_to=PathRename("profile_pics/"), blank=True)
    avatar_config = models.JSONField(
        default=dict, blank=True)  # Contains the avatar builder config
    
    
    class DisplayLanguageChoices(models.TextChoices):
        GERMAN = "de", pgettext_lazy("profile.display-language.de", "German")
        ENGLISH = "en", pgettext_lazy("profile.display-language.en", "English")
        
    display_language = models.CharField(
        choices=DisplayLanguageChoices.choices,
        default=DisplayLanguageChoices.GERMAN,
        max_length=255)

    gender_prediction = models.JSONField(null=True, blank=True)
    
    liability_accepted = models.BooleanField(default=False)

    @classmethod
    def normalize_choice(obj, choice: str):
        ends = [".vol", ".ler"]
        assert any([choice.endswith(c) for c in ends])
        # TODO: somehow catch if dev accidently retused
        # .ler / .vol in profile choice
        return choice.replace(".vol", "").replace(".ler", "")

    def add_profile_picture_from_local_path(self, path):
        print("Trying to add the pic", path)
        self.image.save(os.path.basename(path), File(open(path, 'rb')))
        self.save()

    def check_form_completion(
            self, mark_completed=True,
            set_searching_if_completed=True,
            trigger_score_calulation=True):
        """
        Checks if the userform is completed 
        TODO this could be a little more consize and extract better on which user form page
        the user is currently
        """
        fields_required_for_completion = [
            "lang_level",
            "description",  # This is required but 'language_skill_description' is not!
            "image" if self.image_type == self.ImageTypeChoice.IMAGE else "avatar_config",
            # Postal code is not required anymore
            # *(["postal_code"] if self.partner_location == Profile.normalize_choice(
            #    self.ConversationPartlerLocation.CLOSE_VOL) else []),
            "target_group",
            # 'additional_interests' also not required
            *(["phone_mobile"] if self.notify_channel !=  # phone is only required if notification channel is not email ( so it's sms or phone )
              self.NotificationChannelChoices.EMAIL else []),
        ]
        msgs = []
        is_completed = True
        for field in fields_required_for_completion:
            value = getattr(self, field)
            if value == "":  # TODO: we should also run the serializer
                msgs.append(pgettext_lazy("profile.completion-check.missing-value",
                            "'{val}' is not completed".format(val=field)))
                is_completed = False

        if is_completed and mark_completed:
            self.user.state.set_user_form_completed()

        if is_completed and set_searching_if_completed:
            self.user.state.change_searching_state(
                slug="searching",
                trigger_score_update=trigger_score_calulation)

        return is_completed, msgs

    def save(self, *args, **kwargs):
        """
        Cause we have different choices for language learners 
        and volunteers we need to detect when this is changed.
        If user type is changed we hav to update all choices that have '.vol' or '.ler' ending
        """
        def __ending(vol=True):
            cfield = self.TypeChoices.VOLUNTEER if vol else self.TypeChoices.LEARNER
            return ".vol" if self.user_type == cfield else ".ler"
        choices_different = [  # All choice fields that differe for learners vs volunteers
            'lang_level',
            'partner_location',
            'speech_medium',
            'target_group'
        ]
        allowed_ending = __ending(True)
        disallowed_ending = __ending(False)

        # TODO: we could also only run this if the value of 'user_type' has changed
        for field in choices_different:
            value = getattr(self, field)
            if value.endswith(disallowed_ending):
                # Now we basicly replace disallowed ending with allowed ending
                setattr(self, field, value.replace(
                    disallowed_ending, allowed_ending))

        super(ProfileBase, self).save(*args, **kwargs)


class Profile(ProfileBase):

    user = models.OneToOneField("management.User", on_delete=models.CASCADE)  # Key...


def _date_string():
    # TODO maybe we should add seconds since were using this in combination with unique together
    return datetime.now().strftime("%m/%d/%Y, %H:%M:%S")


class ProfileAtMatchRequest(ProfileBase):
    """
    This model is created everytime a users request a match
    It basicly stores a full copy of the profile when the user asks for a match
    """
    usr_hash = models.CharField(
        max_length=255, unique=False, blank=True, null=True)
    # Sadly we cant use a date field here cause it is not json serializable
    # See https://stackoverflow.com/questions/11875770/how-to-overcome-datetime-datetime-not-json-serializable
    sdate = models.CharField(default=_date_string, max_length=255)

    # But we can add a read date time field without the unique contraint
    # This is convenient for e.g.: sorting in django admin
    date = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['usr_hash', 'date'], name='unique_user_sdate_combination'
            )
        ]


class ProfileSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    interests = serializers.MultipleChoiceField(
        choices=Profile.InterestChoices.choices)
    image = serializers.ImageField(max_length=None, allow_empty_file=True, allow_null=True, required=False)

    def get_options(self, obj):
        d = get_options_serializer(self, obj)
        # There is no way the serializer can determine the options for our availability
        # so lets just add it now, sice availability is stored as json anyways
        # we can easily change the choices here in the future

        if 'availability' in self.Meta.fields:  # <- TODO: does this check work with inheritence?
            d.update({  # Ourcourse there is no need to do this for the Censored profile view
                'availability': {day: [
                    {"value": slot,
                     "tag": SLOT_TRANS[slot]} for slot in SLOTS
                ] for day in DAYS}
            })

        if 'lang_skill' in self.Meta.fields:
            d.update(
                {'lang_skill': {
                    'level': [{'value': l0, 'tag': force_str(l1, strings_only=True)} for l0, l1 in Profile.LanguageSkillChoices.choices],
                    'lang': [{'value': l0, 'tag': force_str(l1, strings_only=True)} for l0, l1 in Profile.LanguageChoices.choices]
                }})

        # TODO: we might want to update the options for than language skill choices also
        return d

    class Meta:
        model = Profile
        fields = '__all__'


class SelfProfileSerializer(ProfileSerializer):
    class Meta:
        model = Profile
        fields = ['first_name', 'second_name', 'target_group', 'speech_medium',
                  'user_type', 'target_group', 'speech_medium',
                  'partner_location', 'postal_code', 'interests', 'availability',
                  'lang_level', 'min_lang_level_partner', 'additional_interests', 'language_skill_description', 'birth_year', 'description',
                  'notify_channel', 'phone_mobile', 'image_type', 'avatar_config', 'image', 'lang_skill', 'gender', 
                  'partner_gender', 'liability_accepted', 'display_language', 'other_target_group', 'target_groups', 'newsletter_subscribed']

        extra_kwargs = dict(
            language_skill_description={
                "error_messages": {
                    'max_length': pgettext_lazy("profile.lskill-descr-to-long",
                                                "must have a maximum of 300 characters"),
                }
            },
            description={
                "error_messages": {
                    'max_length': pgettext_lazy("profile.descr-to-long",
                                                "must have a maximum of 999 characters"),
                }
            }
        )

    def validate(self, data):
        """
        Additional model validation for the profile 
        this is especialy important for the image vs avatar!
        """
        if 'image_type' in data:
            if data['image_type'] == Profile.ImageTypeChoice.IMAGE:
                def __no_img():
                    raise serializers.ValidationError({"image":
                                                       pgettext_lazy(
                                                           "profile.image-missing",
                                                           "You have selected profile image but not uploaded an image")})
                if not 'image' in data:
                    if not self.instance.image:
                        # If the image is not present we only proceede if there is already an image set
                        __no_img()
                elif data['image'] is None:
                    # Only allow removing the image if then the avatar config is set
                    if not 'image_type' in data or not (data['image_type'] == Profile.ImageTypeChoice.AVATAR):
                        raise serializers.ValidationError({"image":
                                                           pgettext_lazy(
                                                               "profile.image-removal-without-avatar",
                                                               "You are removing the profile image but have not selected to use avatar")})
                elif not data['image']:
                    __no_img()
            if data['image_type'] == Profile.ImageTypeChoice.AVATAR:
                if not 'avatar_config' in data or not data['avatar_config']:
                    raise serializers.ValidationError({"avatar_config":
                                                       pgettext_lazy(
                                                           "profile.avatar-missing",
                                                           "You have selected avatar but not uploaded an avatar")})
        return data

    def validate_liability_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                pgettext_lazy("profile.liability-declined",
                              "You must accept the liability"))
        return value

    def validate_postal_code(self, value):
        return validate_postal_code(value)

    def validate_lang_skill(self, value):
        german_level_present = False
        language_count_map = {}
        for lang in value:
            if 'german' in lang['lang']:
                german_level_present = True
            if not (lang['level'] in Profile.LanguageSkillChoices.values):
                raise serializers.ValidationError(
                    pgettext_lazy("profile.lang-level-invalid",
                                  "Invalid language level selected"))

            if not (lang['lang'] in Profile.LanguageChoices.values):
                raise serializers.ValidationError(
                    pgettext_lazy("profile.lang-invalid",
                                  "Invalid language selected"))

            if not lang['lang'] in language_count_map:
                language_count_map[lang['lang']] = 1
            else:
                language_count_map[lang['lang']] += 1

        if not all([v <= 1 for v in language_count_map.values()]):
            raise serializers.ValidationError(
                pgettext_lazy("profile.lang-duplicate",
                              "You have selected a language multiple times"))

        if not german_level_present:
            raise serializers.ValidationError(
                pgettext_lazy("profile.lang-de-missing",
                              "You must select at least german as a language"))
        return value

    def validate_description(self, value):
        if len(value) < 10:  # TODO: higher?
            raise serializers.ValidationError(
                pgettext_lazy("profile.descr-to-short",
                              "must have at least 10 characters"))
        return value


class CensoredProfileSerializer(SelfProfileSerializer):
    class Meta:
        model = Profile
        fields = ["first_name", 'interests', 'availability',
                  'notify_channel', 'phone_mobile', 'image_type',
                  'avatar_config', 'image', 'description',
                  'additional_interests', 'language_skill_description']
        # TODO: do we want language_skill_descr... to be included?
        # It is currently used as 'What Do You Expect From The Talks?' in the main frontend
        
        
class MinimalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["first_name", 'second_name', 'image_type',
                  'avatar_config', 'image', 'description', 'user_type']

class ProposalProfileSerializer(SelfProfileSerializer):
    class Meta:
        model = Profile
        fields = ["first_name", 'availability', 'image_type',
                  'avatar_config', 'image', 'description']