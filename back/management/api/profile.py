import urllib.parse
from dataclasses import dataclass

from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import authentication, permissions, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from translations import get_translation

from back.utils import transform_add_options_serializer
from management.models.profile import Profile, SelfProfileSerializer
from management.models.state import State


@dataclass
class ProfileViewSetParams:
    options: bool = False


class ProfileViewSetSerializer(serializers.Serializer):
    options = serializers.BooleanField(required=False)

    def create(self, validated_data):
        return ProfileViewSetParams(**validated_data)  # type: ignore


class ProfileViewSet(viewsets.GenericViewSet, viewsets.mixins.UpdateModelMixin):
    """
    A viewset for viewing and editing user instances.
    """

    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SelfProfileSerializer

    @extend_schema(
        request=ProfileViewSetSerializer(many=False),
        parameters=[
            OpenApiParameter(
                name=k,
                description="Use this and every self field will contain possible choices in 'options'"
                if k == "options"
                else "",
                required=False,
                type=type(getattr(ProfileViewSetParams, k)),
            )
            for k in ProfileViewSetParams.__annotations__.keys()
        ],
    )
    def _get(self, request):
        serializer = ProfileViewSetSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        _s = SelfProfileSerializer
        if params.options:
            _s = transform_add_options_serializer(_s)

        return Response(_s(getattr(self.request.user, "profile")).data)

    def get_object(self):
        return self.get_queryset()[0]

    def partial_update(self, request, pk=None):
        # assert not pk
        pk = self.request.user.pk
        self.kwargs["pk"] = 1
        return super().partial_update(request, pk=pk)

    def get_queryset(self):
        user = self.request.user
        return [getattr(user, "profile")]


class ProfileCompletedApi(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Checks if a users profile is completed
        and returns a description of what is missing if not
        """
        completed, info = request.user.profile.check_form_completion()
        if completed:
            # If it is completed we store set the state to completet asual!
            user = request.user
            state = user.state
            state.set_user_form_completed()
            state.searching_state = State.SearchingStateChoices.SEARCHING
            state.save()
            default_message = get_translation("auto_messages.prematching_invitation", lang="de").format(
                first_name=user.profile.first_name,
                encoded_params=urllib.parse.urlencode(
                    {
                        "email": str(user.email),
                        "hash": str(user.hash),
                        "bookingcode": str(user.state.prematch_booking_code),
                    }
                ),
                calcom_meeting_id=settings.DJ_CALCOM_MEETING_ID,
            )
            german_level = list(filter(lambda x: x["lang"] == "german", user.profile.lang_skill))[0]["level"]
            if german_level == Profile.LanguageSkillChoices.LEVEL_0:
                default_message = get_translation("auto_messages.prematching_lang_level_too_low", lang="de").format(
                    first_name=user.profile.first_name
                )

            user.message(default_message, auto_mark_read=True, send_message_incoming=True)

            from management.api.user_data_v3 import get_user_data

            ud = get_user_data(user)
            return Response(ud)
        else:
            return Response(info, status=status.HTTP_400_BAD_REQUEST)
