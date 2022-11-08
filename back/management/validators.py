from django.utils.translation import gettext as _
from rest_framework import serializers


def validate_name(value: str):
    """
    Check that value is a valid name.
    """

    if not value.isalpha():
        raise serializers.ValidationError(
            _("Name contains invalid characters"))
    return value
