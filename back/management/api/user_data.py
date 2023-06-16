import django.contrib.auth.password_validation as pw_validation
from copy import deepcopy
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from datetime import datetime
from django.conf import settings
from copy import deepcopy
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
from back.utils import transform_add_options_serializer
from rest_framework.permissions import IsAuthenticated
from django.core.paginator import Paginator
from ..models import (
    SelfNotificationSerializer, NotificationSerializer, Notification,
    ProfileSerializer, SelfProfileSerializer,
    UserSerializer, SelfUserSerializer,
    StateSerializer, SelfStateSerializer,
    CensoredUserSerializer,
    CensoredProfileSerializer,
    SelfSettingsSerializer
)
from .community_events import get_all_comunity_events_serialized
from management.models.unconfirmed_matches import get_unconfirmed_matches

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
    # Serializers with '_' wont be included in the standart user data serialization
    # --> notifications for example are handled and paginated seperately
    "_notifications": SelfNotificationSerializer,
    "settings": SelfSettingsSerializer
}

admin_serializers = {
    "user": UserSerializer,
    "profile": ProfileSerializer,
    "state": StateSerializer,
    "_notifications": NotificationSerializer
}

# For 'other' users
other_serializers = {
    "user": CensoredUserSerializer,
    "profile": CensoredProfileSerializer
    # They do not get the user state at all!
}


@dataclass
class UserDataApiParams:
    page: int = 1  # todo should me "m_page"
    paginate_by: int = 20
    noti_paginate_by: int = 20
    noti_page: int = 1
    options: bool = False


class UserDataApiSerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=False)
    paginate_by = serializers.IntegerField(min_value=1, required=False)
    noti_page = serializers.IntegerField(min_value=1, required=False)
    noti_paginate_by = serializers.IntegerField(min_value=1, required=False)
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
        # This is a simple hack to create a clone of the standart serializer that included the 'options' field
        _serializers = _serializers.copy()
        for _model in ["profile", "state"]:
            _serializers[_model] = transform_add_options_serializer(
                _serializers[_model])
    models = get_user_models(user)  # user, profile, state

    def _maybe_delete_options(d):
        # The admin model included options by default so we can delte them here
        # TODO: there might a sligh performance gain if we have another serializer without the options
        # But that would make the code a bunch longer
        if not include_options and 'options' in d:
            del d['options']
            return d
        return d
    user_data = {}
    for k in _serializers:
        if not k.startswith("_"):
            user_data[k] = _maybe_delete_options(
                _serializers[k](models[k]).data)
    return user_data


def get_matches_paginated(user, admin=False,
                          page=UserDataApiParams.page,
                          paginate_by=UserDataApiParams.paginate_by):
    """
    This returns a list of matches for a user, 
    this will always the censored *except* if accessed by an admin
    """

    pages = Paginator(user.get_matches(), paginate_by).page(page)
    return [get_user_data(p, is_self=False, admin=admin) for p in pages]


def get_matches_paginated_extra_details(user, admin=False,
                                        page=UserDataApiParams.page,
                                        paginate_by=UserDataApiParams.paginate_by):

    paginator = Paginator(user.get_matches(), paginate_by)
    pages = paginator.page(page)

    return [get_user_data(p, is_self=False, admin=admin) for p in pages], {
        "page": page,
        "num_pages": paginator.num_pages,
        "paginate_by": paginate_by,
    }


def get_notifications_paginated(user,
                                admin=False,
                                page=UserDataApiParams.noti_page,
                                paginate_by=UserDataApiParams.noti_paginate_by):
    """
    This returns a list of notifications for that user
    """
    _serializer = (admin_serializers if admin else self_serializers)[
        "_notifications"]
    return [_serializer(p).data for p in Paginator(user.get_notifications(), paginate_by).page(page)]


class SelfInfo(APIView):
    authentication_classes = [authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        """ simple api to fetch your own user info """
        return Response(get_user_data(request.user, is_self=True))


def get_user_data_and_matches(user, options=False, admin=False,
                              page=UserDataApiParams.page,
                              paginate_by=UserDataApiParams.paginate_by,
                              noti_page=UserDataApiParams.page,
                              noti_paginate_by=UserDataApiParams.paginate_by):
    match_data, extra_info = get_matches_paginated_extra_details(
        user, admin=admin, page=page, paginate_by=paginate_by)
    user_and_match_data = {
        **get_user_data(user, is_self=True, include_options=options),
        "matches": match_data,
        "notifications": get_notifications_paginated(user, admin=admin, page=noti_page, paginate_by=noti_paginate_by)
    }

    if admin:
        user_and_match_data["extra_info"] = extra_info

    return user_and_match_data


def get_full_frontend_data(user, options=False, admin=False,
                           page=UserDataApiParams.page,
                           paginate_by=UserDataApiParams.paginate_by,
                           noti_page=UserDataApiParams.page,
                           noti_paginate_by=UserDataApiParams.paginate_by):
    """
    Gathers *all* data for the frontend in addition to matches and self info
    there is also data like community_events, frontend_state
    """

    user_data_and_matches = get_user_data_and_matches(user, options=options, admin=admin,
                                                      page=page, paginate_by=paginate_by,
                                                      noti_page=noti_page, noti_paginate_by=noti_paginate_by)
    extra_infos = user_data_and_matches.pop("extra_info", {})

    frontend_data = {
        **user_data_and_matches,
        "community_events": get_all_comunity_events_serialized(),
        "unconfirmed_matches": get_unconfirmed_matches(user),
        # "frontend_state": "",
    }

    if admin:
        frontend_data["admin_infos"] = {
            **extra_infos
        }

    return frontend_data


class UserData(APIView):
    """
    Returns the main application data for a given user.
    Basicly this is the data the main frontend app receives ( there have been some additions check 'get_all_frontend_data' above )
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
            OpenApiParameter(name=k, description="Use this and every self field will contain possible choices in 'options'" if k == "options" else "",
                             required=False, type=type(getattr(UserDataApiParams, k)))
            for k in UserDataApiParams.__annotations__.keys()
        ],
    )
    def get(self, request, format=None):
        serializer = UserDataApiSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        return Response(get_user_data_and_matches(request.user, admin=request.user.is_staff, **{k: getattr(params, k) for k in params.__annotations__}))
