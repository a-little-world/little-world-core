from rest_framework import serializers
from django.core.exceptions import ValidationError
import contextlib
from translations import get_translation


def as_djv(validator):
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
        validate_name(value)


def model_validate_second_name(value: str):
    with dajango_validation():
        validate_name(value)


@contextlib.contextmanager
def dajango_validation():
    try:
        yield None
    except serializers.ValidationError as e:
        raise ValidationError(e.detail)

def validate_name(value: str):
    # 1 - strip leading and ending whitespace and make leading character uppercase
    value = value.strip()
    value = value.title()
    
    # 2 - other actions are performed only temporary for checking
    tmp_value = value
    allowed_chars = ["-", " "]
    for char in allowed_chars:
        # we don't a special caracter to follow a special caracter of it's kind
        if f"{char}{char}" in value:
            raise serializers.ValidationError(get_translation("val.second_name_too_many_spaces"))
        tmp_value = tmp_value.replace(char, "")

    if not tmp_value.isalpha():
        raise serializers.ValidationError(get_translation("val.second_name_unallowed_chars"))
    return value


def validate_postal_code(value: str):
    value = value.strip()
    if not value.isnumeric():
        raise serializers.ValidationError(get_translation("val.postal_code_not_numeric"))
    as_int = int(value)
    print("TBS", as_int)
    if as_int > 99999:
        raise serializers.ValidationError(get_translation("val.postal_code_too_big"))
    if as_int < 1000:
        raise serializers.ValidationError(get_translation("val.postal_code_too_small"))
    return value


def validate_year(value: int):
    """validates a valid year"""
    pass  # TODO


DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]
SLOTS = ["08_10", "10_12", "12_14", "14_16", "16_18", "18_20", "20_22"]

SLOT_TRANS = {
    "08_10": get_translation("val.availability.time_slot_08_10"),
    "10_12": get_translation("val.availability.time_slot_10_12"),
    "12_14": get_translation("val.availability.time_slot_12_14"),
    "14_16": get_translation("val.availability.time_slot_14_16"),
    "16_18": get_translation("val.availability.time_slot_16_18"),
    "18_20": get_translation("val.availability.time_slot_18_20"),
    "20_22": get_translation("val.availability.time_slot_20_22"),
}

DAY_TRANS = {
    "mo": get_translation("val.availability.week_day_mo"),
    "tu": get_translation("val.availability.week_day_tu"),
    "we": get_translation("val.availability.week_day_we"),
    "th": get_translation("val.availability.week_day_th"),
    "fr": get_translation("val.availability.week_day_fr"),
    "sa": get_translation("val.availability.week_day_sa"),
    "su": get_translation("val.availability.week_day_su"),
}


def get_default_availability():
    return {d: [] for d in DAYS}


def validate_availability(value: dict):
    for day in DAYS:
        assert day in value
        if day not in value:
            raise serializers.ValidationError(get_translation("val.availability.day_not_in_availability").format(day=day))
        for slot in value[day]:
            if slot not in SLOTS:
                raise serializers.ValidationError(get_translation("val.availability.slot_unknown").format(day=day))
    return value
