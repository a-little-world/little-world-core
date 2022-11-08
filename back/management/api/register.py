import django.contrib.auth.password_validation as pw_validation
from typing import Optional
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from django.utils.translation import gettext as _
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
from django.contrib.auth import get_user_model
from .. import validators


class RegistrationData:
    def __init__(self, email, first_name, second_name, password, birth_year):
        self.email = email
        self.first_name = first_name
        self.second_name = second_name
        self.password = password
        self.birth_year = birth_year


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(
        max_length=150, required=True, validators=[validators.validate_name])
    second_name = serializers.CharField(
        max_length=150, required=True, validators=[validators.validate_name])
    password1 = serializers.CharField(max_length=100, required=True)
    password2 = serializers.CharField(max_length=100, required=True)
    birth_year = serializers.IntegerField(min_value=1900, max_value=2040)

    def create(self, validated_data):
        # Password same validation happens in 'validate()' we need only one password now
        return RegistrationData(
            **{k: v for k, v in validated_data.items() if k not in ["password1", "password2"]},
            password=validated_data['password1'])

    def validate(self, data):
        user = get_user_model()(
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

        # TODO: validate birth_year, maybe enforce min-age
        return super(RegistrationSerializer, self).validate(data)


class Register(APIView):
    """
    Register a user by post request
    """
    permission_classes = []  # Everyone can acess this api
    required_args = ['email', 'first_name',
                     'second_name', 'password1', 'password2', 'birth_year']

    @extend_schema(
        # extra parameters added to the schema
        parameters=[
            OpenApiParameter(
                name=param, description=f'User Profile input {param} for Registration', required=True, type=str)
            for param in required_args
        ],
        description='Little World Registration API',
        auth=None,
        operation_id=None,
        operation=None,
        methods=["POST"]
    )
    @extend_schema(request=RegistrationSerializer(many=False))
    def post(self, request) -> Optional[Response]:
        serializer = RegistrationSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            # Perform registration, send email etc...
            # The types are secure, we checked that using the 'Registration Serializer'
            registration_data = serializer.save()
            user_data_serializer = UserSerializer(data=dict(
                # Currently we don't allow any specific username
                username=registration_data.email,
                email=registration_data.email,
                first_name=registration_data.first_name,
                second_name=registration_data.second_name,
                password=registration_data.password
            ))  # type: ignore
            if user_data_serializer.is_valid():
                get_user_model().objects.create(
                    **user_data_serializer.data
                )
            else:
                # In this case we don't raise and execption!
                # because we wan't to rename the validated fields first!
                # e.g.: rename username -> email ( we use username as email but the user doesn't know that )
                # TODO: we should maybe also overwrite some of the messages
                _errors = user_data_serializer.errors
                _errors["email"] = _errors.pop("username")
                return Response(_errors, status=status.HTTP_400_BAD_REQUEST)
            return Response("Sucessfully Created User")
