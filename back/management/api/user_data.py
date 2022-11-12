import django.contrib.auth.password_validation as pw_validation
from copy import deepcopy
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from datetime import datetime
from django.conf import settings
from django.core import exceptions
from django.utils.module_loading import import_string
from rest_framework.decorators import api_view, schema, throttle_classes, permission_classes
from rest_framework import authentication, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from rest_framework import serializers
from rest_framework.throttling import UserRateThrottle
from dataclasses import dataclass
from rest_framework.permissions import IsAuthenticated
from django.core.paginator import Paginator
from ..models import (
    ProfileSerializer, SelfProfileSerializer,
    UserSerializer, SelfUserSerializer,
    StateSerializer, SelfStateSerializer,
    CensoredUserSerializer,
    CensoredProfileSerializer
)

from ..controller import get_user_models

# For the current user
"""
Serializers to be used by the current user or an admin
user -> models.user.User
profile -> models.profile.Profile
state -> models.state.State
settings -> models.settings.Settings
"""
self_serializers = {
    "user": SelfUserSerializer,
    "profile": SelfProfileSerializer,
    "state": SelfStateSerializer,
    # "settings" # TODO create
}

admin_serializers = {
    "user": UserSerializer,
    "profile": ProfileSerializer,
    "state": StateSerializer,
}
# For 'other' users
other_serializers = {
    "user": CensoredUserSerializer,
    "profile": CensoredProfileSerializer
    # They do not get the user state at all!
}


@dataclass
class UserDataApiParams:
    page: int = 1
    paginate_by: int = 20
    options: bool = False


class UserDataApiSerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=False)
    paginate_by = serializers.IntegerField(min_value=1, required=False)
    options = serializers.BooleanField(required=False)

    def create(self, validated_data):
        return UserDataApiParams(**validated_data)  # type: ignore


def get_user_data(user, is_self=False, admin=False, include_options=False):
    """ 
    user: some user
    is_self: if the user is asking for himself ( or an admin is asking )
    This contains all data from all acessible user models
    if the request user is not the same user we censor the profile data by usin another serializer
    """
    _serializers = other_serializers
    if is_self:
        _serializers = self_serializers
    if admin:
        _serializers = admin_serializers
    if include_options:
        _serializers['profile'] = deepcopy(_serializers['profile'])
        _serializers['profile'].Meta.fields.append("options")
    models = get_user_models(user)  # user, profile, state
    return {k: _serializers[k](models[k]).data for k in _serializers}


def get_matches_paginated(user, admin=False,
                          page=UserDataApiParams.page,
                          paginate_by=UserDataApiParams.paginate_by):
    """
    This returns a list of matches for a user, 
    this will always the censored *except* if accessed by an admin
    """
    user_querry = ""  # Get the queryset ... TODO
    pages = Paginator(user_querry, paginate_by).page(page)
    return [get_user_data(user, is_self=True, admin=admin) for p in pages]


class SelfInfo(APIView):
    authentication_classes = [authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    """ simple api to fetch your own user info """

    def get(self, request, format=None):
        return Response(get_user_data(request.user, is_self=True))


class UserData(APIView):
    """
    Returns the main application data for a given user.
    Basicly this is the data the main frontend app receives
    optional params for paginating the matches:
        page: what page to return, default 1
        paginate_by: what number of users per page ( realy only relevant for admins )
    """
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=UserDataApiSerializer(many=False),
        parameters=[
            OpenApiParameter(name=k, description="",
                             required=False, type=type(getattr(UserDataApiParams, k)))
            for k in UserDataApiParams.__annotations__.keys()
        ],
    )
    def get(self, request, format=None):
        serializer = UserDataApiSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        return Response({
            "self": get_user_data(request.user, is_self=True, include_options=params.options),
            "matches": get_matches_paginated(
                request.user,
                admin=request.user.is_staff,
                page=params.page,
                paginate_by=params.paginate_by
            ),
        })
