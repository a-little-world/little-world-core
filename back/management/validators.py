from django.utils.translation import pgettext_lazy, gettext_lazy as _
from rest_framework import serializers
from django.core.exceptions import ValidationError
import contextlib


def as_djv(validator):
    """
    Converts a rest framework validator to a django model validator
    Does this by siply cating rest validaton erros and outputing them as django validation errors
    ---> Will display same validation messages in admin pannel, as on registration form
    """
    def _validate(value):
        try:
            validator(value)
        except serializers.ValidationError as e:
            raise ValidationError(str(e))
    return _validate


def decorate_djv(validator):
    def wrapper(value, *args, **kwargs):
        try:
            validator(value)
        except serializers.ValidationError as e:
            raise ValidationError(str(e))
    return wrapper


def model_validate_first_name(value: str):
    with dajango_validation():
        validate_first_name(value)


def model_validate_second_name(value: str):
    with dajango_validation():
        validate_second_name(value)


@contextlib.contextmanager
def dajango_validation():
    try:
        yield None
    except serializers.ValidationError as e:
        raise ValidationError(e.detail)


def validate_first_name(value: str):
    """
    Normalize a first_name and check if it is valid
    """

    value = value.strip()
    value = value.title()

    if not value.isalpha():
        invalid_chars = [c for c in value if not c.isalpha()]
        print(invalid_chars)
        raise serializers.ValidationError(
            pgettext_lazy("val.first-name-unallowed-chars",
                          "First name contains invalid characters: {chars}".format(chars=','.join(invalid_chars))))
    return value


def validate_second_name(value: str):
    value = value.strip()
    value = value.title()
    amnt_spaces = value.count(" ")
    if amnt_spaces > 1:
        raise serializers.ValidationError(
            pgettext_lazy("val.second-name-too-many-spaces",
                          "It is maximum one space allowed in the Second Name, but you have {count}".format(count=amnt_spaces)))
    _value = value.replace(" ", "")  # <-- So this doesn't error on spaces
    if not _value.isalpha():
        raise serializers.ValidationError(
            pgettext_lazy("val.second-name-unallowed-chars",
                          "Second name contains invalid characters"))
    return value


def validate_postal_code(value: str):
    value = value.strip()
    if not value.isnumeric():
        raise serializers.ValidationError(
            pgettext_lazy("val.postal-code-not-numeric",
                          "German postalcode should be a number"))
    as_int = int(value)
    print("TBS", as_int)
    if as_int > 99999:
        raise serializers.ValidationError(
            pgettext_lazy("val.postal-code-too-big",
                          "German postalcode should have maximum 5 digits"))
    if as_int < 1000:
        raise serializers.ValidationError(
            pgettext_lazy("val.postal-code-too-small",
                          "Postalcode impossibly small"))
    return value


def validate_year(value: int):
    """ validates a valid year """
    pass  # TODO


DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]
SLOTS = ["08_10", "10_12", "12_14", "14_16", "16_18", "18_20", "20_22"]

SLOT_TRANS = {
    "08_10": pgettext_lazy("val.availability.time-slot-08-10", "8 to 10 a.m."),
    "10_12": pgettext_lazy("val.availability.time-slot-10-12", "10 to 12 p.m."),
    "12_14": pgettext_lazy("val.availability.time-slot-12-14", "12 to 2 p.m."),
    "14_16": pgettext_lazy("val.availability.time-slot-14-16", "2 to 4 p.m."),
    "16_18": pgettext_lazy("val.availability.time-slot-16-18", "4 to 6 p.m."),
    "18_20": pgettext_lazy("val.availability.time-slot-18-20", "6 to 8 p.m."),
    "20_22": pgettext_lazy("val.availability.time-slot-20-22", "8 to 10 p.m.")
}

DAY_TRANS = {
    "mo": pgettext_lazy("val.availability.week-day-mo", "Monday"),
    "tu": pgettext_lazy("val.availability.week-day-tu", "Tuesday"),
    "we": pgettext_lazy("val.availability.week-day-we", "Wednesday"),
    "th": pgettext_lazy("val.availability.week-day-th", "Thursday"),
    "fr": pgettext_lazy("val.availability.week-day-fr", "Friday"),
    "sa": pgettext_lazy("val.availability.week-day-sa", "Saturday"),
    "su": pgettext_lazy("val.availability.week-day-su", "Sunday")
}


def get_default_availability():
    return {d: [] for d in DAYS}


def validate_availability(value: dict):
    """
    Validates the availability field
    1 - check that all the day keys are availabol
    2 - check that all time slots are possible
    """
    for day in DAYS:
        assert day in value
        if not day in value:
            raise serializers.ValidationError(
                _("Day '%s' not present in availability!" % day))
        for slot in value[day]:
            if not slot in SLOTS:
                raise serializers.ValidationError(
                    _("Slot '%s' is unknown!" % day))
    return value
