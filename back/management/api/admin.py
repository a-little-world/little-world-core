"""
Contains all the admin apis
generally all APIViews here are required to have: permission_classes = [ IsAdminUser ]
"""
from management.views import admin_panel_v2
from back.utils import CoolerJson
import json
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
from management.models.user import (
    User,
)
from management.models.rooms import (
    Room
)
from management.models.state import (
    StateSerializer,
    State
)
from management.models.profile import (
    Profile,
    ProfileSerializer,
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
    send_email: Optional[bool] = True
    send_message: Optional[bool] = True
    send_notification: Optional[bool] = True
    proposal_only: Optional[bool] = False
    recalc_matching_score: Optional[bool] = True


class TwoUserInputSerializer(serializers.Serializer):
    user1 = serializers.CharField(required=True)
    user2 = serializers.CharField(required=True)
    lookup = serializers.CharField(required=False)
    force = serializers.BooleanField(required=False)
    send_email = serializers.BooleanField(required=False)
    send_message = serializers.BooleanField(required=False)
    send_notification = serializers.BooleanField(required=False)
    proposal_only = serializers.BooleanField(required=False)
    recalc_matching_score = serializers.BooleanField(required=False)

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
    permission_classes = [admin_panel_v2.IsAdminOrMatchingUser]

    @extend_schema(
        request=TwoUserInputSerializer(many=False),
    )
    def post(self, request):
        serializer = TwoUserInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()
        users = get_two_users(params.user1, params.user2, params.lookup)

        from ..models.matching_scores import MatchinScore
        
        # TODO: there should also be a test for this:
        # We check if this is not a staff user then it **has** to be a matching user
        # If it is a matching user we **need** to check if that usee is allowed to manage the requested user! TODO
        if not request.user.is_staff:
            assert request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER), "User is not allowed to match users"
            assert users[0] in request.user.state.managed_users.all(), "User is not allowed to match users"
            assert users[1] in request.user.state.managed_users.all(), "User is not allowed to match users"

        # Load the current matching state and repond with an error if they are not matchable
        dir1 = None
        dir2 = None
        if params.recalc_matching_score:

            from ..matching.matching_score import calculate_directional_score_write_results_to_db

            try:
                dir1 = calculate_directional_score_write_results_to_db(
                    users[0], users[1], return_on_nomatch=False,
                    catch_exceptions=True)
                dir2 = calculate_directional_score_write_results_to_db(
                    users[1], users[0], return_on_nomatch=False,
                    catch_exceptions=True)
            except Exception as e:
                if params.force is None or not params.force:
                    return Response(_("Unable to recalucate matching score! Error: ") + str(e) + " " + MATCH_BY_FORCE_MSG,
                                    status=status.HTTP_400_BAD_REQUEST)
        else:
            try:
                dir1 = MatchinScore.get_current_directional_score(
                    users[0], users[1])
                dir2 = MatchinScore.get_current_directional_score(
                    users[1], users[0])
            except:
                if params.force is None or not params.force:
                    return Response(_("Can't extract matchable info for users, seems like the score calulation failed. This is an idicator that the users are possible unmatchable, if you are sure you want to continue use: ") + MATCH_BY_FORCE_MSG,
                                    status=status.HTTP_400_BAD_REQUEST)

        if not params.force:
            if not (dir1 and dir2):
                return Response({
                    "msg": _("Directional matching score doesnt seem to exist, not sure if users are matchable. Either request to calculate it or set the 'force' flag to true and match anyways"),
                })
            if not (dir1.matchable and dir2.matchable):
                return Response({
                    "message": _("Users score marks users as not matchable with message") + MATCH_BY_FORCE_MSG,
                    "user1_user2_msg": {"msg": dir1.messages, "view": f"{settings.BASE_URL}/admin/management/matchinscore/{dir1.pk}"},
                    "user2_user1_msg": {"msg": dir2.messages, "view": f"{settings.BASE_URL}/admin/management/matchinscore/{dir2.pk}"},
                },
                    status=status.HTTP_400_BAD_REQUEST)

        # Also check if the users are already matched
        if controller.are_users_matched({users[0], users[1]}):
            return Response(_("Users are already matched"), status=status.HTTP_400_BAD_REQUEST)

        if params.proposal_only:
            # If proposal_only = True, we create a proposed match instead!
            # TODO: does this correctly check for already existing proposals?
            proposal = controller.create_user_matching_proposal(
                {users[0], users[1]},
                send_confirm_match_email=params.send_email,
            )

            from management.models import ConsumerConnections, CensoredProfileSerializer
            from management.api.user_data import serialize_proposed_matches

            learner = proposal.get_learner()
            matches = serialize_proposed_matches([proposal], learner)
            payload = {
                "action": "addMatch", 
                "payload": {
                    "category": "proposed",
                    "match": json.loads(json.dumps(matches[0], cls=CoolerJson))
                }
            }
            ConsumerConnections.notify_connections(learner, event="reduction", payload=payload)
            
            # On a maching proposal we only need to notify the learner
            return Response("Matching Proposal Created")
        else:
            # Perform an actual matching!
            match_obj = controller.match_users({users[0], users[1]},
                                   send_email=params.send_email,
                                   send_message=params.send_message,
                                   send_notification=params.send_notification)

            # Now we still need to set the user to no searching anymore
            users[0].state.change_searching_state(
                State.MatchingStateChoices.IDLE)
            users[1].state.change_searching_state(
                State.MatchingStateChoices.IDLE)
            
            # Now notify that users connections
            from management.models import ConsumerConnections, CensoredProfileSerializer
            from management.api.user_data import serialize_matches

            for i in [0, 1]:
                matches = serialize_matches([match_obj], users[i])
                payload = {
                    "action": "addMatch", 
                    "payload": {
                        "category": "unconfirmed",
                        "match": json.loads(json.dumps(matches[0], cls=CoolerJson))
                    }
                }
                ConsumerConnections.notify_connections(users[i], event="reduction", payload=payload)
            return Response(_("Users sucessfully matched"))



@dataclass
class UnmatchUsersParams:
    user1: str
    user2: str
    lookup: str = "hash"
    delete_video_room: bool = True
    delete_dialog: bool = True


class UnmatchUsersInputSerializer(serializers.Serializer):
    user1 = serializers.CharField(required=True)
    user2 = serializers.CharField(required=True)
    lookup = serializers.CharField(required=False, default="hash")
    delete_video_room = serializers.BooleanField(required=False)
    delete_dialog = serializers.BooleanField(required=False)

    def create(self, validated_data):
        return UnmatchUsersParams(**validated_data)


class UnmatchUsers(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=UnmatchUsersInputSerializer(many=False),
    )
    def post(self, request):
        serializer = UnmatchUsersInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()
        users = get_two_users(params.user1, params.user2, params.lookup)

        try:
            controller.unmatch_users(
                {users[0], users[1]}, params.delete_video_room, params.delete_dialog)
        except Exception as e:
            return Response("Unmatching error:" + str(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(_("Users sucessfully un-matched"))


@dataclass
class OneUserInputData:
    user: str
    filters: 'Optional[list[str]]' = None
    invalidate_all_old_scores: bool = False
    lookup: str = "hash"


class OneUserSerializer(serializers.Serializer):
    user = serializers.CharField(required=True)
    lookup = serializers.CharField(required=False)
    invalidate_all_old_scores = serializers.BooleanField(required=False)
    filters = serializers.ListField(required=False)

    def create(self, validated_data):
        return OneUserInputData(**validated_data)


class RequestMatchingScoreUpdate(APIView):

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=OneUserSerializer(many=False),
    )
    def post(self, request):
        from ..tasks import calculate_directional_matching_score_background

        serializer = OneUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        user = controller.get_user(params.user, lookup=params.lookup)
        x = calculate_directional_matching_score_background.delay(
            user.hash,
            filter_slugs=params.filters,
            invalidate_other_scores=params.invalidate_all_old_scores
        )

        return Response({
            "msg": "Task dispatched scores will be written to db on task completion",
            "task_id": x.task_id,
            "view": f"/admin/django_celery_results/taskresult/?q={x.task_id}"
        })


@dataclass
class UserTaggingParams:
    user: str
    tag: str
    action: str = "toggle"  # toggle / add / remove
    lookup: str = "hash"


class UserTaggingSerializer(serializers.Serializer):
    tag = serializers.CharField(required=True)
    user = serializers.CharField(required=True)
    lookup = serializers.CharField(required=False)

    def create(self, validated_data):
        return UserTaggingParams(**validated_data)


class UserTaggingApi(APIView):

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=UserTaggingSerializer(many=False),
    )
    def post(self, request, **kwargs):

        serializer = UserTaggingSerializer(
            data=request.data)  # type: ignore
        serializer.is_valid(raise_exception=True)

        params = serializer.save()
        params.action = kwargs.get("action", params.action)

        user = controller.get_user(params.user, lookup=params.lookup)
        assert params.tag in State.TagChoices.values, "Tag not found"

        if params.action == "toggle":
            if params.tag in user.state.tags:
                user.state.tags.remove(params.tag)
            else:
                user.state.tags.append(params.tag)
            user.state.save()
            return Response({"mas": "Tag toggled:" + str(user.state.tags), "tags": user.state.tags})
        else:
            raise Exception("Not implemented")


class UserModificationAction(APIView):  # TODO:
    """
    put to user/notify
    This is to be used if an admin user wan't to berfor a modification to one or more users
    """
    pass
