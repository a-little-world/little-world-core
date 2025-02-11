from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import django.contrib.auth.password_validation as pw_validation
from django.conf import settings
from django.contrib.auth import login
from django.core import exceptions
from django.utils import translation
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from translations import get_translation

from management.api.user_data import frontend_data
from management.models.user import User

from .. import controller, validators


@dataclass
class RegistrationData:
    email: str
    first_name: str
    second_name: str
    password: str
    birth_year: str
    newsletter_subscribed: bool

    company: str = ""


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        error_messages={
            "blank": get_translation("register.email_blank_err"),  # Updated key
        },
    )

    first_name = serializers.CharField(
        max_length=150,
        required=True,
        error_messages={
            "blank": get_translation("register.first_name_blank_err"),  # Updated key
        },
    )
    second_name = serializers.CharField(
        max_length=150,
        required=True,
        error_messages={
            "blank": get_translation("register.second_name_blank_err"),  # Updated key
        },
    )
    password1 = serializers.CharField(max_length=100, required=True)
    password2 = serializers.CharField(max_length=100, required=True)
    birth_year = serializers.IntegerField(
        min_value=1900,
        max_value=(datetime.now().year - 17),
        error_messages={
            "invalid": get_translation("register.birth_year_invalid"),  # Updated key
            "min_value": get_translation("register.birth_year_under_1900"),  # Updated key
            "max_value": get_translation("register.birth_year_over_2024"),  # Updated key
        },
    )

    newsletter_subscribed = serializers.BooleanField(required=False, default=False)
    company = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    def create(self, validated_data):
        # Password same validation happens in 'validate()' we need only one password now
        return RegistrationData(
            **{k: v for k, v in validated_data.items() if k not in ["password1", "password2"]},
            password=validated_data["password1"],
        )

    def validate_email(self, value):
        # we strip spaces at beginning and end ( cause many people accidently have those )
        value = value.strip()
        return value.lower()

    def validate_first_name(self, value):
        return validators.validate_name(value)

    def validate_second_name(self, value):
        return validators.validate_name(value)

    def validate(self, data):
        usr = None
        try:
            usr = controller.get_user_by_email(data["email"])
        except:
            pass  # If this doesnt fail the user doesn't exist!

        if usr is not None:
            raise serializers.ValidationError(
                {"email": get_translation("api.register_user_email_exists")}
            )  # Updated key

        user = User(username=data["email"], email=data["email"], first_name=data["first_name"])
        try:
            pw_validation.validate_password(password=data["password1"], user=user)
        # the exception raised here is different than serializers.ValidationError
        except exceptions.ValidationError as e:
            raise serializers.ValidationError({"password1": list(e.messages)})

        if data["password1"] != data["password2"]:
            raise serializers.ValidationError({"password1": get_translation("api.passwords_must_match")})  # Updated key

        return super(RegistrationSerializer, self).validate(data)


class Register(APIView):
    """
    Register a user by post request
    """

    authentication_classes = []  # No authentication required, TODO: cors should still be enabled right?
    permission_classes = []  # Everyone can acess this api
    required_args = ["email", "first_name", "second_name", "password1", "password2", "birth_year"]

    @extend_schema(
        description="Little World Registration API called with data from the registration form",
        methods=["POST"],
        request=RegistrationSerializer(many=False),
    )
    def post(self, request) -> Optional[Response]:
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The types are secure, we checked that using the 'Registration Serializer'
        registration_data = serializer.save()

        # create_user will trow seralization error per default
        # also performs registration, send email etc...
        usr = controller.create_user(
            **{k: getattr(registration_data, k) for k in registration_data.__annotations__}, send_verification_mail=True
        )

        if settings.IS_PROD:
            from ..tasks import dispatch_admin_email_notification

            dispatch_admin_email_notification.delay(
                "New user registered",
                f"{registration_data.email}, {registration_data.first_name}, {registration_data.second_name}, {registration_data.birth_year}",
            )

        login(request, usr)

        with translation.override("tag"):
            data = frontend_data(usr)

        return Response(data)
