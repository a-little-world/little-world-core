import os

from django.core.files import File
from django.db import models
from django.utils.deconstruct import deconstructible
from django.utils.encoding import force_str
from multiselectfield import MultiSelectField
from phonenumber_field.modelfields import PhoneNumberField
from rest_framework import serializers
from translations import get_translation

from back.utils import _double_uuid, get_options_serializer
from management.validators import (
    DAYS,
    SLOT_TRANS,
    SLOTS,
    get_default_availability,
    model_validate_first_name,
    model_validate_second_name,
    validate_availability,
    validate_postal_code,
)

# This can be used to handle changes in the api from the frontend
PROFILE_MODEL_VERSION = "1"


def base_lang_skill():
    return []


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


class Profile(models.Model):
    """
    Abstract base class for the default Profile Model
    Note: this represents the **current** profile
    this is not necessarily identical to the profile the user had when looking for his match!
    See the `ProfileAtMatchRequest` model for that
    """

    class Meta:
        app_label = "management"

    version = models.CharField(default=PROFILE_MODEL_VERSION, max_length=255)
    user = models.OneToOneField("management.User", on_delete=models.CASCADE)  # Key...

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

    user_type = models.CharField(choices=TypeChoices.choices, default=TypeChoices.LEARNER, max_length=255)

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

    target_groups = MultiSelectField(choices=TargetGroupChoices2.choices, max_choices=20, max_length=1000, blank=True)  # type: ignore

    # DEPRICATED!!! replaced with 'partner_gender'
    class ParterSexChoice(models.TextChoices):
        ANY = "any", get_translation("profile.partner_sex.any")
        MALE = "male", get_translation("profile.partner_sex.male")
        FEMALE = "female", get_translation("profile.partner_sex.female")

    # DEPRICATED!!! replaced with 'partner_gender'
    partner_sex = models.CharField(choices=ParterSexChoice.choices, default=ParterSexChoice.ANY, max_length=255)

    class PartnerGenderChoices(models.TextChoices):
        ANY = "any", get_translation("profile.partner_gender.any")
        MALE = "male", get_translation("profile.partner_gender.male")
        FEMALE = "female", get_translation("profile.partner_gender.female")
        DIVERSE = "diverse", get_translation("profile.partner_gender.diverse")

    class GenderChoices(models.TextChoices):
        ANY = "any", get_translation("profile.gender.any")
        MALE = "male", get_translation("profile.gender.male")
        FEMALE = "female", get_translation("profile.gender.female")
        DIVERSE = "diverse", get_translation("profile.gender.diverse")

    gender = models.CharField(choices=GenderChoices.choices, default=None, null=True, max_length=255)

    partner_gender = models.CharField(
        choices=PartnerGenderChoices.choices,
        default=PartnerGenderChoices.ANY,
        max_length=255,
    )

    """
    Which medium the user preferes for
    """

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

    job_search = models.BooleanField(blank=True, null=True)
    job_skill_description = models.TextField(default="", blank=True, max_length=300)

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

    interests = MultiSelectField(choices=InterestChoices.choices, max_choices=20, max_length=1000, blank=True)  # type: ignore

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
    language_skill_description = models.TextField(default="", blank=True, max_length=300)

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
    
    class CountryChoices(models.TextChoices):
        AFGHANISTAN = "AF", get_translation("profile.country.af")
        ALAND_ISLANDS = "AX", get_translation("profile.country.ax")
        ALBANIA = "AL", get_translation("profile.country.al")
        ALGERIA = "DZ", get_translation("profile.country.dz")
        AMERICAN_SAMOA = "AS", get_translation("profile.country.as")
        ANDORRA = "AD", get_translation("profile.country.ad")
        ANGOLA = "AO", get_translation("profile.country.ao")
        ANGUILLA = "AI", get_translation("profile.country.ai")
        ANTARCTICA = "AQ", get_translation("profile.country.aq")
        ANTIGUA_AND_BARBUDA = "AG", get_translation("profile.country.ag")
        ARGENTINA = "AR", get_translation("profile.country.ar")
        ARMENIA = "AM", get_translation("profile.country.am")
        ARUBA = "AW", get_translation("profile.country.aw")
        AUSTRALIA = "AU", get_translation("profile.country.au")
        AUSTRIA = "AT", get_translation("profile.country.at")
        AZERBAIJAN = "AZ", get_translation("profile.country.az")
        BAHAMAS = "BS", get_translation("profile.country.bs")
        BAHRAIN = "BH", get_translation("profile.country.bh")
        BANGLADESH = "BD", get_translation("profile.country.bd")
        BARBADOS = "BB", get_translation("profile.country.bb")
        BELARUS = "BY", get_translation("profile.country.by")
        BELGIUM = "BE", get_translation("profile.country.be")
        BELIZE = "BZ", get_translation("profile.country.bz")
        BENIN = "BJ", get_translation("profile.country.bj")
        BERMUDA = "BM", get_translation("profile.country.bm")
        BHUTAN = "BT", get_translation("profile.country.bt")
        BOLIVIA = "BO", get_translation("profile.country.bo")
        BONAIRE_SINT_EUSTATIUS_AND_SABA = "BQ", get_translation("profile.country.bq")
        BOSNIA_AND_HERZEGOVINA = "BA", get_translation("profile.country.ba")
        BOTSWANA = "BW", get_translation("profile.country.bw")
        BOUVET_ISLAND = "BV", get_translation("profile.country.bv")
        BRAZIL = "BR", get_translation("profile.country.br")
        BRITISH_INDIAN_OCEAN_TERRITORY = "IO", get_translation("profile.country.io")
        BRUNEI_DARUSSALAM = "BN", get_translation("profile.country.bn")
        BULGARIA = "BG", get_translation("profile.country.bg")
        BURKINA_FASO = "BF", get_translation("profile.country.bf")
        BURUNDI = "BI", get_translation("profile.country.bi")
        CAMBODIA = "KH", get_translation("profile.country.kh")
        CAMEROON = "CM", get_translation("profile.country.cm")
        CANADA = "CA", get_translation("profile.country.ca")
        CAPE_VERDE = "CV", get_translation("profile.country.cv")
        CAYMAN_ISLANDS = "KY", get_translation("profile.country.ky")
        CENTRAL_AFRICAN_REPUBLIC = "CF", get_translation("profile.country.cf")
        CHAD = "TD", get_translation("profile.country.td")
        CHILE = "CL", get_translation("profile.country.cl")
        CHINA = "CN", get_translation("profile.country.cn")
        CHRISTMAS_ISLAND = "CX", get_translation("profile.country.cx")
        COCOS_KEELING_ISLANDS = "CC", get_translation("profile.country.cc")
        COLOMBIA = "CO", get_translation("profile.country.co")
        COMOROS = "KM", get_translation("profile.country.km")
        CONGO = "CG", get_translation("profile.country.cg")
        CONGO_DEMOCRATIC_REPUBLIC_OF_THE_CONGO = "CD", get_translation("profile.country.cd")
        COOK_ISLANDS = "CK", get_translation("profile.country.ck")
        COSTA_RICA = "CR", get_translation("profile.country.cr")
        COTE_D_IVOIRE = "CI", get_translation("profile.country.ci")
        CROATIA = "HR", get_translation("profile.country.hr")
        CUBA = "CU", get_translation("profile.country.cu")
        CURACAO = "CW", get_translation("profile.country.cw")
        CYPRUS = "CY", get_translation("profile.country.cy")
        CZECH_REPUBLIC = "CZ", get_translation("profile.country.cz")
        DENMARK = "DK", get_translation("profile.country.dk")
        DJIBOUTI = "DJ", get_translation("profile.country.dj")
        DOMINICA = "DM", get_translation("profile.country.dm")
        DOMINICAN_REPUBLIC = "DO", get_translation("profile.country.do")
        ECUADOR = "EC", get_translation("profile.country.ec")
        EGYPT = "EG", get_translation("profile.country.eg")
        EL_SALVADOR = "SV", get_translation("profile.country.sv")
        EQUATORIAL_GUINEA = "GQ", get_translation("profile.country.gq")
        ERITREA = "ER", get_translation("profile.country.er")
        ESTONIA = "EE", get_translation("profile.country.ee")
        ETHIOPIA = "ET", get_translation("profile.country.et")
        ESWATINI = "SZ", get_translation("profile.country.sz")
        FALKLAND_ISLANDS_MALVINAS = "FK", get_translation("profile.country.fk")
        FAROE_ISLANDS = "FO", get_translation("profile.country.fo")
        FIJI = "FJ", get_translation("profile.country.fj")
        FINLAND = "FI", get_translation("profile.country.fi")
        FRANCE = "FR", get_translation("profile.country.fr")
        FRENCH_GUIANA = "GF", get_translation("profile.country.gf")
        FRENCH_POLYNESIA = "PF", get_translation("profile.country.pf")
        FRENCH_SOUTHERN_TERRITORIES = "TF", get_translation("profile.country.tf")
        GABON = "GA", get_translation("profile.country.ga")
        GAMBIA = "GM", get_translation("profile.country.gm")
        GEORGIA = "GE", get_translation("profile.country.ge")
        GERMANY = "DE", get_translation("profile.country.de")
        GHANA = "GH", get_translation("profile.country.gh")
        GIBRALTAR = "GI", get_translation("profile.country.gi")
        GREECE = "GR", get_translation("profile.country.gr")
        GREENLAND = "GL", get_translation("profile.country.gl")
        GRENADA = "GD", get_translation("profile.country.gd")
        GUADELOUPE = "GP", get_translation("profile.country.gp")
        GUAM = "GU", get_translation("profile.country.gu")
        GUATEMALA = "GT", get_translation("profile.country.gt")
        GUERNSEY = "GG", get_translation("profile.country.gg")
        GUINEA = "GN", get_translation("profile.country.gn")
        GUINEA_BISSAU = "GW", get_translation("profile.country.gw")
        GUYANA = "GY", get_translation("profile.country.gy")
        HAITI = "HT", get_translation("profile.country.ht")
        HEARD_ISLAND_AND_MCDONALD_ISLANDS = "HM", get_translation("profile.country.hm")
        HOLY_SEE_VATICAN_CITY_STATE = "VA", get_translation("profile.country.va")
        HONDURAS = "HN", get_translation("profile.country.hn")
        HONG_KONG = "HK", get_translation("profile.country.hk")
        HUNGARY = "HU", get_translation("profile.country.hu")
        ICELAND = "IS", get_translation("profile.country.is")
        INDIA = "IN", get_translation("profile.country.in")
        INDONESIA = "ID", get_translation("profile.country.id")
        IRAN = "IR", get_translation("profile.country.ir")
        IRAQ = "IQ", get_translation("profile.country.iq")
        IRELAND = "IE", get_translation("profile.country.ie")
        ISLE_OF_MAN = "IM", get_translation("profile.country.im")
        ISRAEL = "IL", get_translation("profile.country.il")
        ITALY = "IT", get_translation("profile.country.it")
        JAMAICA = "JM", get_translation("profile.country.jm")
        JAPAN = "JP", get_translation("profile.country.jp")
        JERSEY = "JE", get_translation("profile.country.je")
        JORDAN = "JO", get_translation("profile.country.jo")
        KAZAKHSTAN = "KZ", get_translation("profile.country.kz")
        KENYA = "KE", get_translation("profile.country.ke")
        KIRIBATI = "KI", get_translation("profile.country.ki")
        NORTH_KOREA = "KP", get_translation("profile.country.kp")
        SOUTH_KOREA = "KR", get_translation("profile.country.kr")
        KOSOVO = "XK", get_translation("profile.country.xk")
        KUWAIT = "KW", get_translation("profile.country.kw")
        KYRGYZSTAN = "KG", get_translation("profile.country.kg")
        LAOS = "LA", get_translation("profile.country.la")
        LATVIA = "LV", get_translation("profile.country.lv")
        LEBANON = "LB", get_translation("profile.country.lb")
        LESOTHO = "LS", get_translation("profile.country.ls")
        LIBERIA = "LR", get_translation("profile.country.lr")
        LIBYAN_ARAB_JAMAHIRIYA = "LY", get_translation("profile.country.ly")
        LIECHTENSTEIN = "LI", get_translation("profile.country.li")
        LITHUANIA = "LT", get_translation("profile.country.lt")
        LUXEMBOURG = "LU", get_translation("profile.country.lu")
        MACAO = "MO", get_translation("profile.country.mo")
        MADAGASCAR = "MG", get_translation("profile.country.mg")
        MALAWI = "MW", get_translation("profile.country.mw")
        MALAYSIA = "MY", get_translation("profile.country.my")
        MALDIVES = "MV", get_translation("profile.country.mv")
        MALI = "ML", get_translation("profile.country.ml")
        MALTA = "MT", get_translation("profile.country.mt")
        MARSHALL_ISLANDS = "MH", get_translation("profile.country.mh")
        MARTINIQUE = "MQ", get_translation("profile.country.mq")
        MAURITANIA = "MR", get_translation("profile.country.mr")
        MAURITIUS = "MU", get_translation("profile.country.mu")
        MAYOTTE = "YT", get_translation("profile.country.yt")
        MEXICO = "MX", get_translation("profile.country.mx")
        MICRONESIA_FEDERATED_STATES_OF = "FM", get_translation("profile.country.fm")
        MOLDOVA = "MD", get_translation("profile.country.md")
        MONACO = "MC", get_translation("profile.country.mc")
        MONGOLIA = "MN", get_translation("profile.country.mn")
        MONTENEGRO = "ME", get_translation("profile.country.me")
        MONTSERRAT = "MS", get_translation("profile.country.ms")
        MOROCCO = "MA", get_translation("profile.country.ma")
        MOZAMBIQUE = "MZ", get_translation("profile.country.mz")
        MYANMAR = "MM", get_translation("profile.country.mm")
        NAMIBIA = "NA", get_translation("profile.country.na")
        NAURU = "NR", get_translation("profile.country.nr")
        NEPAL = "NP", get_translation("profile.country.np")
        NETHERLANDS = "NL", get_translation("profile.country.nl")
        NEW_CALEDONIA = "NC", get_translation("profile.country.nc")
        NEW_ZEALAND = "NZ", get_translation("profile.country.nz")
        NICARAGUA = "NI", get_translation("profile.country.ni")
        NIGER = "NE", get_translation("profile.country.ne")
        NIGERIA = "NG", get_translation("profile.country.ng")
        NIUE = "NU", get_translation("profile.country.nu")
        NORFOLK_ISLAND = "NF", get_translation("profile.country.nf")
        NORTH_MACEDONIA = "MK", get_translation("profile.country.mk")
        NORTHERN_MARIANA_ISLANDS = "MP", get_translation("profile.country.mp")
        NORWAY = "NO", get_translation("profile.country.no")
        OMAN = "OM", get_translation("profile.country.om")
        PAKISTAN = "PK", get_translation("profile.country.pk")
        PALAU = "PW", get_translation("profile.country.pw")
        PALESTINE = "PS", get_translation("profile.country.ps")
        PANAMA = "PA", get_translation("profile.country.pa")
        PAPUA_NEW_GUINEA = "PG", get_translation("profile.country.pg")
        PARAGUAY = "PY", get_translation("profile.country.py")
        PERU = "PE", get_translation("profile.country.pe")
        PHILIPPINES = "PH", get_translation("profile.country.ph")
        PITCAIRN = "PN", get_translation("profile.country.pn")
        POLAND = "PL", get_translation("profile.country.pl")
        PORTUGAL = "PT", get_translation("profile.country.pt")
        PUERTO_RICO = "PR", get_translation("profile.country.pr")
        QATAR = "QA", get_translation("profile.country.qa")
        REUNION = "RE", get_translation("profile.country.re")
        ROMANIA = "RO", get_translation("profile.country.ro")
        RUSSIA = "RU", get_translation("profile.country.ru")
        RWANDA = "RW", get_translation("profile.country.rw")
        SAINT_BARTHELEMY = "BL", get_translation("profile.country.bl")
        SAINT_HELENA = "SH", get_translation("profile.country.sh")
        SAINT_KITTS_AND_NEVIS = "KN", get_translation("profile.country.kn")
        SAINT_LUCIA = "LC", get_translation("profile.country.lc")
        SAINT_MARTIN = "MF", get_translation("profile.country.mf")
        SAINT_PIERRE_AND_MIQUELON = "PM", get_translation("profile.country.pm")
        SAINT_VINCENT_AND_THE_GRENADINES = "VC", get_translation("profile.country.vc")
        SAMOA = "WS", get_translation("profile.country.ws")
        SAN_MARINO = "SM", get_translation("profile.country.sm")
        SAO_TOME_AND_PRINCIPE = "ST", get_translation("profile.country.st")
        SAUDI_ARABIA = "SA", get_translation("profile.country.sa")
        SENEGAL = "SN", get_translation("profile.country.sn")
        SERBIA = "RS", get_translation("profile.country.rs")
        SEYCHELLES = "SC", get_translation("profile.country.sc")
        SIERRA_LEONE = "SL", get_translation("profile.country.sl")
        SINGAPORE = "SG", get_translation("profile.country.sg")
        SINT_MAARTEN = "SX", get_translation("profile.country.sx")
        SLOVAKIA = "SK", get_translation("profile.country.sk")
        SLOVENIA = "SI", get_translation("profile.country.si")
        SOLOMON_ISLANDS = "SB", get_translation("profile.country.sb")
        SOMALIA = "SO", get_translation("profile.country.so")
        SOUTH_AFRICA = "ZA", get_translation("profile.country.za")
        SOUTH_GEORGIA_AND_THE_SOUTH_SANDWICH_ISLANDS = "GS", get_translation("profile.country.gs")
        SOUTH_SUDAN = "SS", get_translation("profile.country.ss")
        SPAIN = "ES", get_translation("profile.country.es")
        SRI_LANKA = "LK", get_translation("profile.country.lk")
        SUDAN = "SD", get_translation("profile.country.sd")
        SURINAME = "SR", get_translation("profile.country.sr")
        SVALBARD_AND_JAN_MAYEN = "SJ", get_translation("profile.country.sj")
        SWEDEN = "SE", get_translation("profile.country.se")
        SWITZERLAND = "CH", get_translation("profile.country.ch")
        SYRIA = "SY", get_translation("profile.country.sy")
        TAIWAN = "TW", get_translation("profile.country.tw")
        TAJIKISTAN = "TJ", get_translation("profile.country.tj")
        TANZANIA_UNITED_REPUBLIC_OF = "TZ", get_translation("profile.country.tz")
        THAILAND = "TH", get_translation("profile.country.th")
        TIMOR_LESTE = "TL", get_translation("profile.country.tl")
        TOGO = "TG", get_translation("profile.country.tg")
        TOKELAU = "TK", get_translation("profile.country.tk")
        TONGA = "TO", get_translation("profile.country.to")
        TRINIDAD_AND_TOBAGO = "TT", get_translation("profile.country.tt")
        TUNISIA = "TN", get_translation("profile.country.tn")
        TURKIYE = "TR", get_translation("profile.country.tr")
        TURKMENISTAN = "TM", get_translation("profile.country.tm")
        TURKS_AND_CAICOS_ISLANDS = "TC", get_translation("profile.country.tc")
        TUVALU = "TV", get_translation("profile.country.tv")
        UGANDA = "UG", get_translation("profile.country.ug")
        UKRAINE = "UA", get_translation("profile.country.ua")
        UNITED_ARAB_EMIRATES = "AE", get_translation("profile.country.ae")
        UNITED_KINGDOM = "GB", get_translation("profile.country.gb")
        UNITED_STATES = "US", get_translation("profile.country.us")
        UNITED_STATES_MINOR_OUTLYING_ISLANDS = "UM", get_translation("profile.country.um")
        URUGUAY = "UY", get_translation("profile.country.uy")
        UZBEKISTAN = "UZ", get_translation("profile.country.uz")
        VANUATU = "VU", get_translation("profile.country.vu")
        VENEZUELA = "VE", get_translation("profile.country.ve")
        VIET_NAM = "VN", get_translation("profile.country.vn")
        VIRGIN_ISLANDS_BRITISH = "VG", get_translation("profile.country.vg")
        VIRGIN_ISLANDS_U_S = "VI", get_translation("profile.country.vi")
        WALLIS_AND_FUTUNA = "WF", get_translation("profile.country.wf")
        WESTERN_SAHARA = "EH", get_translation("profile.country.eh")
        YEMEN = "YE", get_translation("profile.country.ye")
        ZAMBIA = "ZM", get_translation("profile.country.zm")
        ZIMBABWE = "ZW", get_translation("profile.country.zw")
        
    country_of_residence = models.CharField(choices=CountryChoices.choices, default=CountryChoices.GERMANY, max_length=255)

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

    image_type = models.CharField(choices=ImageTypeChoice.choices, default=ImageTypeChoice.IMAGE, max_length=255)
    image = models.ImageField(upload_to=PathRename("profile_pics/"), blank=True)
    avatar_config = models.JSONField(default=dict, blank=True)  # Contains the avatar builder config

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

    push_notifications_enabled = models.BooleanField(default=False)

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
            "image" if self.image_type == self.ImageTypeChoice.IMAGE else "avatar_config",
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
                msgs.append(get_translation("profile.completion_check.missing_value").format(val=field))
                is_completed = False

        if is_completed and mark_completed:
            self.user.state.set_user_form_completed()

        if is_completed and set_searching_if_completed:
            self.user.state.change_searching_state(slug="searching", trigger_score_update=trigger_score_calulation)

        return is_completed, msgs


class ProfileSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    interests = serializers.MultipleChoiceField(choices=Profile.InterestChoices.choices)
    target_groups = serializers.MultipleChoiceField(choices=Profile.TargetGroupChoices2.choices)
    image = serializers.ImageField(max_length=None, allow_empty_file=True, allow_null=True, required=False)

    def get_options(self, obj):
        d = get_options_serializer(self, obj)
        # There is no way the serializer can determine the options for our availability
        # so let's just add it now, since availability is stored as JSON anyways
        # we can easily change the choices here in the future

        if "availability" in self.Meta.fields:  # <- TODO: does this check work with inheritance?
            d.update(
                {  # Our course there is no need to do this for the Censored profile view
                    "availability": {day: [{"value": slot, "tag": SLOT_TRANS[slot]} for slot in SLOTS] for day in DAYS}
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
        
        if "country_of_residence" in self.Meta.fields:
            d.update(
                {
                    "country_of_residence": [
                        {"value": c0, "tag": force_str(c1, strings_only=True)}
                        for c0, c1 in Profile.CountryChoices.choices
                    ]
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
            "country_of_residence",
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
            "push_notifications_enabled",
            "job_search",
            "job_skill_description",
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
                    raise serializers.ValidationError({"image": get_translation("profile.image_missing")})

                if "image" not in data:
                    if not self.instance.image:
                        # If the image is not present we only proceed if there is already an image set
                        __no_img()
                elif data["image"] is None:
                    # Only allow removing the image if then the avatar config is set
                    if "image_type" not in data or not (data["image_type"] == Profile.ImageTypeChoice.AVATAR):
                        raise serializers.ValidationError(
                            {"image": get_translation("profile.image_removal_without_avatar")}
                        )
                elif not data["image"]:
                    __no_img()
            if data["image_type"] == Profile.ImageTypeChoice.AVATAR:
                if "avatar_config" not in data or not data["avatar_config"]:
                    raise serializers.ValidationError({"avatar_config": get_translation("profile.avatar_missing")})
        return data

    def validate_liability_accepted(self, value):
        if not value:
            raise serializers.ValidationError(get_translation("profile.liability_declined"))
        return value

    def validate_postal_code(self, value):
        return validate_postal_code(value)

    def validate_interests(self, value):
        if len(value) < 3:
            raise serializers.ValidationError(get_translation("profile.interests.min_number"))
        return value

    def validate_availability(self, value):
        # Count total entries across all arrays in the availability object
        total_entries = sum(len(entries) for entries in value.values())

        if total_entries < 3:
            raise serializers.ValidationError(get_translation("profile.availability.min_number"))
        return value

    def validate_target_groups(self, value):
        if len(value) < 1:
            raise serializers.ValidationError(get_translation("profile.target_groups.min_number"))
        return value

    def validate_lang_skill(self, value):
        german_level_present = False
        language_count_map = {}
        for lang in value:
            if "german" in lang["lang"]:
                german_level_present = True
            if lang["level"] not in Profile.LanguageSkillChoices.values:
                raise serializers.ValidationError(get_translation("profile.lang_level_invalid"))

            if lang["lang"] not in Profile.LanguageChoices.values:
                raise serializers.ValidationError(get_translation("profile.lang_invalid"))

            if lang["lang"] not in language_count_map:
                language_count_map[lang["lang"]] = 1
            else:
                language_count_map[lang["lang"]] += 1

        if not all([v <= 1 for v in language_count_map.values()]):
            raise serializers.ValidationError(get_translation("profile.lang_duplicate"))

        if not german_level_present:
            raise serializers.ValidationError(get_translation("profile.lang_de_missing"))
        return value

    def validate_description(self, value):
        if len(value) < 10:  # TODO: higher?
            raise serializers.ValidationError(get_translation("profile.descr_too_short"))
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
            "lang_skill",
            "interests",
            "image_type",
            "avatar_config",
            "image",
            "description",
            "user_type",
            "target_group",
            "target_groups",
            "partner_gender",
            "newsletter_subscribed",
            "phone_mobile",
            "push_notifications_enabled",
            "job_search",
            "job_skill_description",
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
            "user_type",
        ]

