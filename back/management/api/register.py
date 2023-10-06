from drf_spectacular.utils import OpenApiParameter, OpenApiExample
import django.contrib.auth.password_validation as pw_validation
from django.contrib.auth import authenticate, login
from typing import Optional
from django.utils.translation import pgettext_lazy, gettext_lazy as _
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from datetime import datetime
from django.conf import settings
from django.core import exceptions
from django.utils.module_loading import import_string
from rest_framework import status
from rest_framework.decorators import api_view, schema, throttle_classes, permission_classes
from rest_framework import authentication, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from ..models import ProfileSerializer, UserSerializer
from dataclasses import dataclass
from .. import validators, controller
from ..models.user import User
from . import schemas


@dataclass
class RegistrationData:
    email: str
    first_name: str
    second_name: str
    password: str
    birth_year: str


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, error_messages={
        'blank': pgettext_lazy('register.email-blank-err', 'Please enter your e-mail adress'),
        # 'invalid' --> The message here is quite ok, so I'll just keep using it!
    })

    first_name = serializers.CharField(max_length=150, required=True, error_messages={
        'blank': pgettext_lazy('register.first-name-blank-err', 'Please enter your first name'),
    })
    second_name = serializers.CharField(max_length=150, required=True, error_messages={
        'blank': pgettext_lazy('register.second-name-blank-err', 'Please enter your second name'),
    })
    password1 = serializers.CharField(max_length=100, required=True)
    password2 = serializers.CharField(max_length=100, required=True)
    birth_year = serializers.IntegerField(min_value=1900, max_value=(datetime.now().year - 17), error_messages={
        'invalid': pgettext_lazy('register.birth-year-invalid', 'Please enter a valid year'),
        'min_value': pgettext_lazy('register.birth-year-under-1900', 'I\'m sorry but you can\'t be that old'),
        'max_value': pgettext_lazy('register.birth-year-over-2024', 'Sorry currently users have to be at least 18 years old to participate'),
    })

    def create(self, validated_data):
        # Password same validation happens in 'validate()' we need only one password now
        return RegistrationData(
            **{k: v for k, v in validated_data.items() if k not in ["password1", "password2"]},
            password=validated_data['password1'])

    def validate_email(self, value):
        # we strip spaces at beginning and end ( cause many people accidently have those )
        value = value.strip()
        return value.lower()

    def validate_first_name(self, value):
        return validators.validate_first_name(value)

    def validate_second_name(self, value):
        return validators.validate_second_name(value)

    def validate(self, data):

        usr = None
        try:
            usr = controller.get_user_by_email(data['email'])
        except:
            pass  # If this doesnt fail the user doesn't exist!

        if not usr is None:
            raise serializers.ValidationError(
                {"email": pgettext_lazy("api.register-user-email-exists", "User with this email already exists")})

        user = User(
            username=data['email'],
            email=data['email'],
            first_name=data['first_name']
        )
        try:
            pw_validation.validate_password(
                password=data['password1'], user=user)
        # the exception raised here is different than serializers.ValidationError
        except exceptions.ValidationError as e:
            raise serializers.ValidationError(
                {"password1": list(e.messages)})

        if data['password1'] != data['password2']:
            raise serializers.ValidationError(
                {"password1": _("Passwords must match")})

        return super(RegistrationSerializer, self).validate(data)


class Register(APIView):
    """
    Register a user by post request
    """
    authentication_classes = [
    ]  # No authentication required, TODO: cors should still be enabled right?
    permission_classes = []  # Everyone can acess this api
    required_args = ['email', 'first_name', 'second_name',
                     'password1', 'password2', 'birth_year']

    @extend_schema(
        description='Little World Registration API called with data from the registration form',
        methods=["POST"],
        request=RegistrationSerializer(many=False)
    )
    def post(self, request) -> Optional[Response]:
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The types are secure, we checked that using the 'Registration Serializer'
        registration_data = serializer.save()

        # create_user will trow seralization error per default
        # also performs registration, send email etc...
        usr = controller.create_user(**{k: getattr(registration_data, k) for k in registration_data.__annotations__},
                                     send_verification_mail=True, check_prematching_invitations=True)

        if settings.IS_PROD:
            from ..tasks import dispatch_admin_email_notification
            dispatch_admin_email_notification.delay(
                "New user registered", f"{registration_data.email}, {registration_data.first_name}, {registration_data.second_name}, {registration_data.birth_year}")
        try:
            login(request, usr)  # this errors in tests, if used as function
        except Exception as e:
            print("Auto login failed: {}".format(repr(e)))
            return Response("User cerated but auto login failed")
        return Response("Sucessfully Created User")
