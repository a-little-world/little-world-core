from django.utils.translation import gettext as _
from rest_framework import serializers


def validate_name(value: str):
    """ Check that value is a valid name """
    if not value.isalpha():
        raise serializers.ValidationError(
            _("Name contains invalid characters"))
    return value


def validate_year(value: int):
    """ validates a valid year """
    pass  # TODO


DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]
SLOTS = ["08_10", "10_12", "12_14", "14_16", "16_18", "18_20", "20_22"]


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
