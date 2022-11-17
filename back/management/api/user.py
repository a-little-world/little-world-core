from rest_framework.views import APIView
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from management.controller import get_user_by_hash
from rest_framework.response import Response
from django.contrib.auth import authenticate, login
from ..models.state import State
from rest_framework import serializers, status
from dataclasses import dataclass
from tracking.models import Event
from tracking import utils
"""
The public /user api's

`user/get` and `user/list` are only available for admins (`admin/` prefix) see api.admin
"""


class VerifyEmail(APIView):

    # Everyone can acess this 'get' api,
    # we will enforce authentication for 'post' though
    permission_classes = []

    def get(self, request, **kwargs):
        """
        this can be called by non authenticated users, 
        e.g.: they verify email from their phone but are logged in on PC
        we will then assume 'auth_data' is a base64 encoded string
        """
        if not 'auth_data' in kwargs:
            raise serializers.ValidationError(
                {"auth_data": _("Must be part of url path!")})
        try:
            _data = State.decode_email_auth_code_b64(kwargs.get('auth_data'))
            usr = get_user_by_hash(_data['u'])
            if usr.state.check_email_auth_code_b64(kwargs['auth_data']):
                return Response(_("Email sucessfully verified"))
        except Exception as e:
            print(repr(e))
        return Response(_("Email verification failed"), status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, **kwargs):
        """
        This would be used if the user wan't to use pin authentication
        in this case we need to check if the user is authenticated first ( since .get is an open api )
        we will then assume 'auth_data' is a 6 digit verification pin
        """
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_403_FORBIDDEN)
        if not 'auth_data' in kwargs:
            raise serializers.ValidationError(
                {"auth_data": _("Must be part of url path!")})
        if request.user.state.check_email_auth_pin(int(kwargs['auth_data'])):
            return Response(_("Email sucessfully verified"))
        return Response(_("Email verification failed"), status=status.HTTP_400_BAD_REQUEST)


@dataclass
class LoginData:
    email: str
    password: str


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)

    def create(self, validated_data):
        return LoginData(**validated_data)


@extend_schema(
    request=LoginSerializer(many=False)
)
class LoginApi(APIView):
    permission_classes = []
    authentication_classes = []

    @utils.track_event(
        name=_("User Logged in"),
        event_type=Event.EventTypeChoices.REQUEST,
        tags=["frontend", "login", "sensitive"],
        censor_kwargs=["password"])
    def post(self, request):
        """
        This is to login regular users only!!!! 
        Admins are not allowed to login here, see section `Security` of the README.md
        """
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login_data = serializer.save()

        usr = authenticate(username=login_data.email,
                           password=login_data.password)

        if usr is not None:
            if usr.is_staff:
                return Response(_("Login failed"), status=status.HTTP_400_BAD_REQUEST)
            login(request, usr)
            return Response(_("Login sucessfull"))
        else:
            return Response(_("Login failed"), status=status.HTTP_400_BAD_REQUEST)
