from rest_framework.views import APIView
from django.utils.translation import pgettext_lazy
from django.contrib.auth import logout
from django_rest_passwordreset.signals import reset_password_token_created
from django.conf import settings
from django.dispatch import receiver
from drf_spectacular.utils import extend_schema
from management.controller import get_user_by_hash, get_user_by_email, UserNotFoundErr
from rest_framework.response import Response
from django.contrib.auth import authenticate, login
from ..models.state import State
from rest_framework import authentication, permissions
from rest_framework import serializers, status
from dataclasses import dataclass
from tracking.models import Event
from tracking import utils
from emails.mails import get_mail_data_by_name, PwResetMailParams
from ..models.state import State
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
                {"auth_data": pgettext_lazy("email.verify-auth-data-missing-get",
                                            "Email authentication data missing")})
        try:
            _data = State.decode_email_auth_code_b64(kwargs['auth_data'])
            usr = get_user_by_hash(_data['u'])
            if usr.state.check_email_auth_code_b64(kwargs['auth_data']):
                return Response(pgettext_lazy("email.verify-success-get",
                                              "Email sucessfully verified"))
        except Exception as e:
            print(repr(e))
        return Response(pgettext_lazy("email.verify-failure-get",
                                      "Email verification failed"),
                        status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, **kwargs):
        """
        This would be used if the user wan't to use pin authentication
        in this case we need to check if the user is authenticated first ( since .get is an open api )
        we will then assume 'auth_data' is a 6 digit verification pin
        """
        if not request.user.is_authenticated:
            # POST is only for logged in users it allowes to enter a PIN
            return Response(status=status.HTTP_403_FORBIDDEN)
        if not 'auth_data' in kwargs:
            raise serializers.ValidationError(
                {"auth_data": pgettext_lazy("email.verify-auth-data-missing-post",
                                            "Email authentication data missing")})
        try:
            auth_pin = int(kwargs['auth_data'])
        except:
            raise serializers.ValidationError({"auth_data":
                                               pgettext_lazy("email.verify-failure-not-numeric",
                                                             "Enter a 5 digit pin please")})
        if request.user.state.check_email_auth_pin(auth_pin):
            return Response(pgettext_lazy("email.verify-success-post",
                                          "Email sucessfully verified"))
        return Response(pgettext_lazy("email.verify-failure-post",
                                      "Email verification failed, wrong code."),
                        status=status.HTTP_400_BAD_REQUEST)


@dataclass
class LoginData:
    email: str
    password: str


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)

    def create(self, validated_data):
        return LoginData(**validated_data)


@extend_schema(request=LoginSerializer(many=False))
class LoginApi(APIView):
    permission_classes = []
    authentication_classes = []

    @utils.track_event(
        name="User Logged in",
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
            if usr.is_staff:  # type: ignore
                # pylint thinks this is a AbsUsr but we have overwritten it models.user.User
                return Response(pgettext_lazy(
                    "api.login-failed-staff", "Can't log in email or password wrong!"),
                    status=status.HTTP_400_BAD_REQUEST)
            login(request, usr)
            return Response(pgettext_lazy(
                "api.login-sucessful", "Sucessfully logged in!"))
        else:
            return Response(pgettext_lazy(
                "api.login-failed", "Can't log-in email or password wrong!"),
                status=status.HTTP_400_BAD_REQUEST)


class LogoutApi(APIView):

    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @utils.track_event(
        name="User Logged out",
        event_type=Event.EventTypeChoices.REQUEST,
        tags=["frontend", "log-out", "sensitive"])
    def get(self, request):

        logout(request)
        return Response(pgettext_lazy(
            "api.logout-sucessful", "Sucessfully logged out!"))


@dataclass
class CheckPwParams:
    password: str
    email: str


class CheckPwSerializer(serializers.Serializer):
    password = serializers.EmailField(required=True)
    email = serializers.EmailField(required=True)

    def create(self, validated_data):
        return CheckPwParams(**validated_data)


# This sorta enables password enumeration but only if one manages to steal a users session token
# TODO So like the login api this should be throttled!
class CheckPasswordApi(APIView):

    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=CheckPwSerializer(many=False))
    def post(self, request):
        serializer = CheckPwSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        _check = request.user.check_password(params.password)
        return Response(status=status.HTTP_200_OK if _check else status.HTTP_400_BAD_REQUEST)


@dataclass
class ChangeEmailParams:
    email: str
    # password: str TODO we might want to allow changing email only with password?


class ChangeEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    # password = serializers.EmailField(required=True)

    def create(self, validated_data):
        return ChangeEmailParams(**validated_data)


class ChangeEmailApi(APIView):

    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ChangeEmailSerializer(many=False))
    def post(self, request):
        """
        The user can use this to change his email, *of couse only if the is logged in*
        we identify the user by his session
        we always store old emails in state.past_emails just to be sure
        NOTE this **will** automaticly set 'state.email_autenticated = False' if email can be changed
        and the user will get another email send
        """
        serializer = ChangeEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        if params.email == request.user.email:
            raise serializers.ValidationError({
                "email": pgettext_lazy(
                    "api.user.change-email-failed.same-email",
                    "This is your current email!"
                )
            })
        else:
            # Maybe a user with this email already exista anyways?
            try:
                get_user_by_email(params.email)
            except UserNotFoundErr:
                raise ValueError({"email":  # TODO: now we are exposing us to email enumeration this APIView should be throttled!
                                  pgettext_lazy("api.user.change-email-failed.email-exists",
                                                "Email {email} exists".format(email=params.email))})

        # Now we change the email, change the auto code & pin, send another verification mail
        request.user.change_email(params.email)
        return Response(pgettext_lazy(
            "api.user.change-email-successful",
            "E-mail adres update, email adress must be reauthenticated."))


@dataclass
class ConfirmMatchesParams:
    matches: 'list[str]'


class ConfirmMatchesSerializer(serializers.Serializer):
    matches = serializers.ListField(required=True)

    def create(self, validated_data):
        return ConfirmMatchesParams(**validated_data)


class ConfirmMatchesApi(APIView):

    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ConfirmMatchesSerializer(many=False))
    def post(self, request):
        serializer = ConfirmMatchesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        try:
            request.user.state.confirm_matches(params.matches)
        except Exception as e:
            raise serializers.ValidationError({"matches": str(e)})

        return Response(pgettext_lazy("api.user-matches-successfully-confirmed",
                                      "Matches confirmed!"))


@dataclass
class SearchingStateApiParams:
    state_slug: str


class SearchingStateApiSerializer(serializers.Serializer):
    state_slug = serializers.CharField(required=True)

    def create(self, validated_data):
        return SearchingStateApiParams(**validated_data)


class UpdateSearchingStateApi(APIView):

    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=SearchingStateApiSerializer(many=False))
    def post(self, request, **kwargs):
        """
        Update the users serching state, current possible states: 'idle', 'searching'
        So e.g.: This should be called then the users clicks on search for match
        """
        serializer = SearchingStateApiSerializer(
            data={'state_slug': kwargs.get('state_slug')} if 'state_slug' in kwargs else {})  # type: ignore
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        print("TBS", State.MatchingStateChoices.values)

        if not params.state_slug in State.MatchingStateChoices.values:
            raise serializers.ValidationError(
                {"state_slug": pgettext_lazy(
                    "api.user-update-searching-state.slug-doesnt-exist",
                    "'{slug}' is not a possible seraching state!".format(slug=params.state_slug))}
            )

        request.user.state.change_searching_state(params.state_slug)
        return Response(pgettext_lazy("api.user-update-searching-state.state-successfully-changed",
                                      "State updated!"))


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, *args, **kwargs):
    """
    Handles password reset tokens
    This is automaticly called fron djang-rest-password reset when the /api/user/resetpw is called
    """
    # TODO: track this event!
    #print("TBS: request PW reset", sender, instance, reset_password_token)
    # This is the url of our password reset view
    # We also pass the reset token to the view so it can be used to change the password
    usr_hash = reset_password_token.user.hash
    reset_password_url = f"{settings.BASE_URL}/set_password/{usr_hash}/{reset_password_token.key}"
    print("GENERATED RESET URL", reset_password_url)

    mail_data = get_mail_data_by_name("password_reset")
    reset_password_token.user.send_email(
        subject=pgettext_lazy("api.user-resetpw.mail-subject", ""),
        mail_data=mail_data,
        mail_params=PwResetMailParams(
            password_reset_url=reset_password_url
        ),
    )
