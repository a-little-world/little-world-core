"""
Contains all the admin apis
generally all APIView here are required to have: permission_classes = [ IsAdminUser ]
"""
from rest_framework.views import APIView
from django.utils.translation import gettext as _
from rest_framework import authentication, permissions
from rest_framework.response import Response
from rest_framework import serializers
from .user_data import get_user_data
from dataclasses import dataclass
from django.core.paginator import Paginator
from .. import controller


@dataclass
class GetUserParams:
    hash: str = ""
    email: str = ""
    pk: str = ""


class GetUserSerialier(serializers.Serializer):
    pk = serializers.IntegerField(required=False)
    hash = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)

    def create(self, validated_data):
        return GetUserParams(**validated_data)


class GetUser(APIView):
    """
    For admins to get a user either by hash, email or pk 
    """
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BaseAuthentication]
    permission_classes = [permissions.IsAdminUser]

    param_names = ["hash", "email", "pk"]

    def get(self, request, format=None):
        serializer = GetUserSerialier(data=request.querry_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()
        # So we can check == "",  also get_user_by_pk accepts string and auto converts to int
        params.pk = str(params.pk)

        empty_params = [getattr(params, n) == "" for n in self.param_names]
        if all(empty_params):
            raise serializers.ValidationError({
                n: _("at least one field required") for n in self.param_names
            })
        if sum(empty_params) > 1:
            raise serializers.ValidationError({
                n: _(f"maximum one field allowed") for n in self.param_names if getattr(params, n) != ""
            })
        lookup = self.param_names[empty_params.index(False)]
        return Response(get_user_data(
            controller.get_user(getattr(params, lookup), lookup=lookup),
            is_self=True  # Cause admins can be who every they want ;)
        ))


@dataclass
class UserListParams:
    filters: 'list[str]' = []
    paginate_by: int = 50
    # TODO: what is default order when not applyin any order to queryset?
    # Prob by key ?
    order_by: str = ""
    page: int = 1


class UserListApiSerializer(serializers.Serializer):
    filters = serializers.ListField(required=False)
    paginate_by = serializers.IntegerField(required=False)
    page = serializers.IntegerField(required=False)
    order_by = serializers.CharField(required=False)

    def create(self, validated_data):
        return UserListParams(**validated_data)


class UserList(APIView):  # TODO:
    """
    Fetches an arbitrary user list, args:
    - filters = []
    - paginate_by = 50
    - order_by = TODO some default
    - page = 1
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        serializer = UserListApiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        user_querry = ""  # Get the queryset ... TODO
        pages = Paginator(user_querry, params.paginate_by).page(params.page)
        return [get_user_data(p, is_self=True) for p in pages]


class MatchingSuggestion(APIView):  # TODO
    pass


class MakeMatch(APIView):  # TODO
    pass


class UserModificationAction(APIView):  # TODO:
    """
    This is to be used if an admin user wan't to berfor a modification to one or more users
    """
    pass

# UserStateViewSet

# UserProfileViewSet

# UserSettingsViewSet
