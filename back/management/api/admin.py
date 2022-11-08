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
from .. import controller


class GetUserParams:
    hash: str = ""
    email: str = ""
    pk: str = ""


class GetUserSerialier(serializers.Serializer):
    pk = serializers.IntegerField(required=False)
    hash = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)

    def create(self, validated_data):
        return GetUserParams(**validated_data)  # type: ignore


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


class UserList(APIView):  # TODO:
    """
    Fetches an arbitrary user list, args:
    - filters = []
    - paginate_by = 50
    - order_by = TODO some default
    - page = 0
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        pass


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
