from django.utils.translation import pgettext_lazy
from rest_framework import serializers


def validate_first_name(value: str):
    """ 
    Normalize a first_name and check if it is valid
    """

    value = value.strip()
    value = value.title()

    if not value.isalpha():
        raise serializers.ValidationError(
            pgettext_lazy("val.first-name-unallowed-chars",
                          "First name contains invalid characters"))
    return value


def validate_second_name(value: str):
    value = value.strip()
    value = value.title()
    amnt_spaces = value.count(" ")
    if amnt_spaces > 1:
        raise serializers.ValidationError(
            pgettext_lazy("val.second-name-too-many-spaces",
                          "It is maximum one space allowed in the Second Name, but you have {count}".format({'count': amnt_spaces})))
    _value = value.replace(" ", "")  # <-- So this doesn't error on spaces
    if not _value.isalpha():
        raise serializers.ValidationError(
            pgettext_lazy("val.second-name-unallowed-chars",
                          "Second name contains invalid characters"))
    return value


def validate_year(value: int):
    """ validates a valid year """
    pass  # TODO


DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]
SLOTS = ["08_10", "10_12", "12_14", "14_16", "16_18", "18_20", "20_22"]


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
