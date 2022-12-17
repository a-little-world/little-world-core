"""
Contains all the admin apis
generally all APIViews here are required to have: permission_classes = [ IsAdminUser ]
"""
from rest_framework.views import APIView
from django.conf import settings
from typing import List, Optional
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework import authentication, permissions
from rest_framework.response import Response
from rest_framework import serializers
from .user_data import get_user_data
from .user_slug_filter_lookup import get_users_by_slug_filter
from ..models import (
    User,
    Profile,
    State,
    Room
)
from dataclasses import dataclass, field
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
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAdminUser]

    param_names = ["hash", "email", "pk"]

    @extend_schema(
        request=GetUserSerialier(many=False),
        parameters=[
            OpenApiParameter(name=param, description="",
                             required=False, type=str)
            for param in param_names
        ],
    )
    def get(self, request, format=None):
        serializer = GetUserSerialier(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()
        # So we can check == "",  also get_user_by_pk accepts string and auto converts to int
        params.pk = str(params.pk)

        empty_params = [getattr(params, n) == "" for n in self.param_names]
        if all(empty_params):
            raise serializers.ValidationError({
                n: _("at least one field required") for n in self.param_names
            })
        if sum([not e for e in empty_params]) > 1:
            print(empty_params)
            raise serializers.ValidationError({
                n: _(f"maximum one field allowed") for n in self.param_names if getattr(params, n) != ""
            })
        lookup = self.param_names[empty_params.index(False)]
        try:
            return Response(get_user_data(
                controller.get_user(getattr(params, lookup), lookup=lookup),
                is_self=True, admin=True  # Cause admins can be who every they want ;)
            ))
        except controller.UserNotFoundErr as e:
            print(f"ERR: {str(e)}")
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)


@dataclass
class UserListParams:
    filters: 'list[str]' = field(default_factory=list)
    paginate_by: int = 50
    order_by: Optional[str] = None  # Use default order per default
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

    e.g.: filters = ['state.user_form_page:is:0']
    """

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=UserListApiSerializer(many=False),
    )
    def post(self, request):
        serializer = UserListApiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        filtered_user_list = list(User.objects.all())

        for filter in params.filters:
            print("Applying filter ", filter)
            filtered_user_list = get_users_by_slug_filter(
                filter_slug=filter, user_to_filter=filtered_user_list)

        pages = Paginator(filtered_user_list,
                          params.paginate_by).page(params.page)
        # We return the full user data for every user
        # TODO: we might want way to limit the amount of data passed here
        return Response([get_user_data(p, is_self=True, admin=True, include_options=False) for p in pages])


class MatchingSuggestion(APIView):  # TODO
    pass


# ==================================== TWO user 'action' apis: ====================================

@dataclass
class TwoUserInputData:
    user1: str
    user2: str
    lookup: str = "hash"  # The user hashes are always default lookup
    force: Optional[bool] = False


class TwoUserInputSerializer(serializers.Serializer):
    user1 = serializers.CharField(required=True)
    user2 = serializers.CharField(required=True)
    lookup = serializers.CharField(required=False)
    force = serializers.BooleanField(required=False)

    def create(self, validated_data):
        return TwoUserInputData(**validated_data)


def get_two_users(usr1, usr2, lookup):
    return [
        controller.get_user(usr1, lookup=lookup),
        controller.get_user(usr2, lookup=lookup),
    ]


MATCH_BY_FORCE_MSG = _(
    "\nIf you are sure you want to match these users anyways, please set the 'force' flag to true")


class MakeMatch(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=TwoUserInputSerializer(many=False),
    )
    def post(self, request):
        serializer = TwoUserInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()
        users = get_two_users(params.user1, params.user2, params.lookup)

        from ..models.matching_scores import MatchinScore

        # Load the current matching state and repond with an error if they are not matchable
        dir1 = None
        dir2 = None
        try:
            dir1 = MatchinScore.get_current_directional_score(
                users[0], users[1])
            dir2 = MatchinScore.get_current_directional_score(
                users[1], users[0])
        except:
            if params.force is None or not params.force:
                return Response(_("Can extract matchable info for users, seems like the score calulation failed. This is an idicator that the users are possible unmatchable, if you are sure you want to continue use: ") + MATCH_BY_FORCE_MSG,
                                status=status.HTTP_400_BAD_REQUEST)

        if not params.force:
            print("DIR")
            assert dir1 and dir2, "respective directional matching scores do not exist!"
            if not dir1.matchable or dir2.matchable:
                return Response({
                    "message": _("Users score marks users as not matchable with message") + MATCH_BY_FORCE_MSG,
                    "user1_user2_msg": {"msg": dir1.messages, "view": f"{settings.BASE_URL}/admin/management/matchinscore/{dir1.pk}"},
                    "user2_user1_msg": {"msg": dir2.messages, "view": f"{settings.BASE_URL}/admin/management/matchinscore/{dir2.pk}"},
                },
                    status=status.HTTP_400_BAD_REQUEST)


class UserModificationAction(APIView):  # TODO:
    """
    put to user/notify
    This is to be used if an admin user wan't to berfor a modification to one or more users
    """
    pass
