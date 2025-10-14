import hashlib
import hmac
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Q
from django.dispatch import receiver
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django_rest_passwordreset.signals import reset_password_token_created
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from emails import mails
from emails.mails import PwResetMailParams, get_mail_data_by_name
from rest_framework import authentication, permissions, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from tracking import utils
from tracking.models import Event
from translations import get_translation

from management.controller import UserNotFoundErr, delete_user, get_user, get_user_by_email, get_user_by_hash
from management.authentication import NativeOnlyJWTAuthentication
from management.models.state import FrontendStatusSerializer, State
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from management.models.profile import SelfProfileSerializer
from management.models.matches import Match
from management.models.banner import Banner, BannerSerializer
from django.db.models import Q

"""
The public /user api's

`user/get` and `user/list` are only available for admins (`admin/` prefix) see api.admin
"""


def verify_email_link(auth_data):
    try:
        _data = State.decode_email_auth_code_b64(auth_data)
        usr = get_user_by_hash(_data["u"])
        if usr.state.check_email_auth_code_b64(auth_data):
            return True
    except Exception as e:
        print(repr(e))
        return False
    return False


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
        if "auth_data" not in kwargs:
            raise serializers.ValidationError({"auth_data": get_translation("email.verify_auth_data_missing_get")})

        if verify_email_link(kwargs["auth_data"]):
            return Response(get_translation("email.verify_success_get"))

        return Response(get_translation("email.verify_failure_get"), status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, **kwargs):
        """
        This would be used if the user wan't to use pin authentication
        in this case we need to check if the user is authenticated first ( since .get is an open api )
        we will then assume 'auth_data' is a 6 digit verification pin
        """
        if not request.user.is_authenticated:
            # POST is only for logged in users it allowes to enter a PIN
            return Response(status=status.HTTP_403_FORBIDDEN)
        if "auth_data" not in kwargs:
            raise serializers.ValidationError({"auth_data": get_translation("email.verify_auth_data_missing_post")})
        try:
            auth_pin = int(kwargs["auth_data"])
        except:
            raise serializers.ValidationError({"auth_data": get_translation("email.verify_failure_not_numeric")})
        if request.user.state.check_email_auth_pin(auth_pin):
            return Response(get_translation("email.verify_success_post"))
        return Response(get_translation("email.verify_failure_post"), status=status.HTTP_400_BAD_REQUEST)


@dataclass
class LoginData:
    email: str
    password: str


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)

    def create(self, validated_data):
        return LoginData(**validated_data)


@dataclass
class ChallengeData:
    challenge: str
    timestamp: int


class ChallengeSerializer(serializers.Serializer):
    challenge = serializers.CharField(required=True)
    timestamp = serializers.IntegerField(required=True)

    def create(self, validated_data):
        return ChallengeData(**validated_data)


@dataclass
class NativeLoginData:
    email: str
    password: str
    challenge: str
    proof: str


class NativeLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)
    challenge = serializers.CharField(required=True)
    proof = serializers.CharField(required=True)

    def create(self, validated_data):
        return NativeLoginData(**validated_data)


@dataclass
class AutoLoginData:
    u: str  # user
    l: str  # lookup: hash | email | id
    token: str  # auto login token
    n: Optional[str] = None  # next page


class AutoLoginSerializer(serializers.Serializer):
    u = serializers.CharField(required=True)
    l = serializers.CharField(required=True)
    n = serializers.CharField(required=False)
    token = serializers.CharField(required=True)

    def create(self, validated_data):
        return AutoLoginData(**validated_data)

class LoginApi(APIView):
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        request=LoginSerializer(many=False),
        parameters=[
            OpenApiParameter(
                name="token_auth",
                description="If true, returns an authentication token instead of creating a session",
                type=bool,
                required=False,
                default=False,
                location=OpenApiParameter.QUERY,
            ),
        ],
    )
    def post(self, request):
        """
        This is to login regular users only!!!!
        Admins are not allowed to login here, see section `Security` of the README.md
        """
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login_data = serializer.save()

        usr = authenticate(username=login_data.email.lower(), password=login_data.password)

        if usr is not None:
            if usr.is_staff:  # type: ignore
                # pylint thinks this is a AbsUsr but we have overwritten it models.user.User
                return Response(get_translation("api.login_failed_staff"), status=status.HTTP_400_BAD_REQUEST)

            # token_auth is a query parameter that determines whether to return a token or create a session
            token_auth = request.query_params.get("token_auth", False)
            if token_auth:
                # Legacy token auth - now deprecated in favor of native challenge-response
                return Response("Token auth deprecated. Use /api/user/native-login for native apps", status=status.HTTP_400_BAD_REQUEST)
            else:
                login(request, usr)
                return Response(get_user_data(request.user))
        else:
            return Response(get_translation("api.login_failed"), status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(request=AutoLoginSerializer(many=False))
    def get(self, request):
        """
        Allowes to authenticate users using the extra auth token
        """
        # if (not settings.IS_DEV) and (not settings.IS_STAGE):
        #    assert False, "For now this api is only available on stage"

        serializer = AutoLoginSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        u = get_user(params.u, params.l)
        if not u.state.has_extra_user_permission(State.ExtraUserPermissionChoices.AUTO_LOGIN):
            return Response("Unauthorized", status=status.HTTP_403_FORBIDDEN)
        else:
            if params.token == u.state.auto_login_api_token:
                login(request, u)
                if params.n is None:
                    return redirect(reverse("management:main_frontend"))
                else:
                    return HttpResponseRedirect(redirect_to=params.n)
        return Response(get_translation("api.auto_login_failed"))


class LogoutApi(APIView):
    authentication_classes = [
        authentication.SessionAuthentication,
        authentication.BasicAuthentication,
        NativeOnlyJWTAuthentication,
    ]
    permission_classes = [permissions.IsAuthenticated]

    @utils.track_event(
        name="User Logged out", event_type=Event.EventTypeChoices.REQUEST, tags=["frontend", "log-out", "sensitive"]
    )
    def get(self, request):
        logout(request)
        return Response(get_translation("api.logout_sucessful"))


@dataclass
class CheckPwParams:
    password: str


class CheckPwSerializer(serializers.Serializer):
    password = serializers.CharField(required=True)

    def create(self, validated_data):
        return CheckPwParams(**validated_data)


class CheckPasswordApi(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=CheckPwSerializer(many=False))
    def post(self, request):
        serializer = CheckPwSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        _check = request.user.check_password(params.password)
        return Response(status=status.HTTP_200_OK if _check else status.HTTP_400_BAD_REQUEST)


@dataclass
class ChangePwParams:
    password_old: str
    password_new: str
    password_new2: str


class ChangePasswordSerializer(serializers.Serializer):
    password_old = serializers.CharField(required=True)
    password_new = serializers.CharField(required=True)
    password_new2 = serializers.CharField(required=True)

    def create(self, validated_data):
        return ChangePwParams(**validated_data)


class ChangePasswordApi(APIView):
    authentication_classes = [
        authentication.SessionAuthentication,
        authentication.BasicAuthentication,
        NativeOnlyJWTAuthentication,
    ]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer(many=False))
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        _check = request.user.check_password(params.password_old)
        if not _check:
            return Response(
                get_translation("api.change_password_failed_incorrect_old_pw"), status=status.HTTP_400_BAD_REQUEST
            )

        if params.password_new != params.password_new2:
            return Response(
                get_translation("api.change_password_failed_new_pw_not_equal"), status=status.HTTP_400_BAD_REQUEST
            )

        request.user.set_password(params.password_new)
        request.user.save()

        return Response(get_translation("api.change_password_sucessful"), status=status.HTTP_200_OK)


@dataclass
class ChangeEmailParams:
    email: str


class ChangeEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        # we strip spaces at beginning and end ( cause many people accidently have those )
        value = value.strip()
        return value.lower()

    def create(self, validated_data):
        return ChangeEmailParams(**validated_data)


class ChangeEmailApi(APIView):
    authentication_classes = [
        authentication.SessionAuthentication,
        authentication.BasicAuthentication,
        NativeOnlyJWTAuthentication,
    ]
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

        if request.user.is_staff:
            raise serializers.ValidationError({"email": get_translation("api.user.change_email_not_allowed_staff")})

        if params.email == request.user.email:
            raise serializers.ValidationError({"email": get_translation("api.user.change_email_failed_same_email")})
        else:
            # Maybe a user with this email already exista anyways?
            email_exists = True
            try:
                get_user_by_email(params.email)
            except UserNotFoundErr:
                email_exists = False
            if email_exists:
                raise serializers.ValidationError(
                    {
                        "email":  # TODO: now we are exposing us to email enumeration this APIView should be throttled!
                        get_translation("api.user.change_email_failed_email_exists").format(email=params.email)
                    }
                )

        # Now we change the email, change the auto code & pin, send another verification mail
        request.user.change_email(params.email)
        return Response(get_translation("api.user.change_email_successful"))


@dataclass
class ConfirmMatchesParams:
    matches: "list[str]"


class ConfirmMatchesSerializer(serializers.Serializer):
    matches = serializers.ListField(required=True)

    def create(self, validated_data):
        return ConfirmMatchesParams(**validated_data)


class ConfirmMatchesApi(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ConfirmMatchesSerializer(many=False))
    def post(self, request):
        serializer = ConfirmMatchesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        try:
            # TODO: this is the old strategy, we should use the new stragegy
            request.user.state.confirm_matches(params.matches)
        except Exception:
            pass

        try:
            # In order to keep things working while we deploy the new strategy this api will also populate all db-fileds required for the new strategy
            # This is a little more involved than it has to be, this will once finished be replaced by 'ConfirmMatchesApi2'
            for match_hash in params.matches:
                partner = get_user_by_hash(match_hash)

                from management.models.matches import Match

                match = Match.get_match(request.user, partner)
                assert match.exists()
                match = match.first()
                match.confirm(request.user)

        except Exception as e:
            raise serializers.ValidationError({"matches": str(e)})

        return Response(get_translation("api.user_matches_successfully_confirmed"))


@dataclass
class SearchingStateApiParams:
    state_slug: str


class SearchingStateApiSerializer(serializers.Serializer):
    state_slug = serializers.CharField(required=True)

    def create(self, validated_data):
        return SearchingStateApiParams(**validated_data)


class UpdateSearchingStateApi(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=SearchingStateApiSerializer(many=False))
    def post(self, request, **kwargs):
        """
        Update the users serching state, current possible states: 'idle', 'searching'
        So e.g.: This should be called then the users clicks on search for match
        """
        serializer = SearchingStateApiSerializer(
            data={"state_slug": kwargs.get("state_slug")} if "state_slug" in kwargs else {}
        )  # type: ignore
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        if params.state_slug not in State.SearchingStateChoices.values:
            raise serializers.ValidationError(
                {
                    "state_slug": get_translation("api.user_update_searching_state_slug_doesnt_exist").format(
                        slug=params.state_slug
                    )
                }
            )

        request.user.state.change_searching_state(params.state_slug)

        if (params.state_slug == State.SearchingStateChoices.SEARCHING) and request.user.state.unresponsive:
            # If the user was manaully set to 'unresponsive' he can self remove this flag by searching him-self again
            request.user.state.unresponsive = False
            request.user.state.save()

        return Response(get_translation("api.user_update_searching_state_state_successfully_changed"))


class UnmatchSelfSerializer(serializers.Serializer):
    other_user_hash = serializers.CharField(required=True)
    reason = serializers.CharField(required=True)

    def create(self, validated_data):
        return validated_data


@login_required
@api_view(["POST"])
def resend_verification_mail(request):
    if settings.USE_V2_EMAIL_APIS:
        request.user.send_email_v2("verify-email")
    else:
        # TODO: depricate the old way
        link_route = "mailverify_link"
        verifiaction_url = f"{settings.BASE_URL}/{link_route}/{request.user.state.get_email_auth_code_b64()}"
        mails.send_email(
            recivers=[request.user.email],
            subject="{code} - Verifizierungscode zur E-Mail Bestätigung".format(
                code=request.user.state.get_email_auth_pin()
            ),
            mail_data=mails.get_mail_data_by_name("welcome"),
            mail_params=mails.WelcomeEmailParams(
                first_name=request.user.profile.first_name,
                verification_url=verifiaction_url,
                verification_code=str(request.user.state.get_email_auth_pin()),
            ),
        )

    return Response("Resend verification mail")


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, *args, **kwargs):
    """
    Handles password reset tokens
    This is automaticly called fron djang-rest-password reset when the /api/user/resetpw is called
    """
    # This is the url of our password reset view
    # We also pass the reset token to the view so it can be used to change the password
    usr_hash = reset_password_token.user.hash
    reset_password_url = f"{settings.BASE_URL}/set_password/{usr_hash}/{reset_password_token.key}"

    if settings.USE_V2_EMAIL_APIS:
        reset_password_token.user.send_email_v2("reset-password", context={"reset_password_url": reset_password_url})
    else:
        mail_data = get_mail_data_by_name("password_reset")
        reset_password_token.user.send_email(
            subject=get_translation("api.user_resetpw_mail_subject"),
            mail_data=mail_data,
            mail_params=PwResetMailParams(password_reset_url=reset_password_url),
        )


@login_required
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def still_active_callback(request):
    us = request.user.state
    us.searching_state = State.SearchingStateChoices.SEARCHING
    us.still_active_reminder_confirmed = True
    us.save()

    return HttpResponseRedirect(redirect_to="/app/chat")


@login_required
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def delete_account(request):
    # Cannot delete staff or matching users with this api!
    assert not request.user.is_staff
    assert not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

    delete_user(request.user, management_user=None, send_deletion_email=True)
    logout(request)

    return Response({"success": True})


def get_user_data(user):
    """
    Returns user data similar to the original user_data function.
    """
    user_state = user.state
    user_profile = user.profile

    pre_match_appointent = None
    pre_matching_app = PreMatchingAppointment.objects.filter(user=user).first()
    if pre_matching_app:
        pre_match_appointent = PreMatchingAppointmentSerializer(pre_matching_app).data

    cal_data_link = "{calcom_meeting_id}?{encoded_params}".format(
        encoded_params=urllib.parse.urlencode(
            {"email": str(user.email), "hash": str(user.hash), "bookingcode": str(user.state.prematch_booking_code)}
        ),
        calcom_meeting_id=settings.DJ_CALCOM_MEETING_ID,
    )

    # Get video call join link if available
    pre_call_join_link = settings.PREMATCHING_CALL_JOIN_LINK
    profile_data = SelfProfileSerializer(user_profile).data

    has_atleast_one_match = Match.objects.filter(
        Q(user1=user) | Q(user2=user),
        support_matching=False,
    ).exists()
    
        # Retrieve the active banner for the specific user type
    banner_query = Banner.get_active_banner(user)

    banner = BannerSerializer(banner_query).data if banner_query else {}

    return {
        "id": str(user.hash),
        "banner": banner,
        "status": FrontendStatusSerializer(user_state).data,
        "isSupport": user_state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
        or user.is_staff,
        "isSearching": user_state.searching_state == State.SearchingStateChoices.SEARCHING,
        "email": user.email,
        "preMatchingAppointment": pre_match_appointent,
        "preMatchingCallJoinLink": pre_call_join_link,
        "calComAppointmentLink": cal_data_link,
        "hadPreMatchingCall": user_state.had_prematching_call,
        "emailVerified": user_state.email_authenticated,
        "userFormCompleted": user_state.user_form_state == State.UserFormStateChoices.FILLED,
        "hasMatch": has_atleast_one_match,
        "profile": profile_data,
    }


@extend_schema(
    responses=inline_serializer(
        name="UserData",
        fields={
            "id": serializers.UUIDField(),
            "status": serializers.CharField(),
            "isSupport": serializers.BooleanField(),
            "isSearching": serializers.BooleanField(),
            "email": serializers.EmailField(),
            "preMatchingAppointment": PreMatchingAppointmentSerializer(required=False),
            "calComAppointmentLink": serializers.CharField(),
            "hadPreMatchingCall": serializers.BooleanField(),
            "emailVerified": serializers.BooleanField(),
            "userFormCompleted": serializers.BooleanField(),
            "hasMatch": serializers.BooleanField(),
            "profile": SelfProfileSerializer(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def user_profile(request):
    """
    Returns user profile data.
    """
    try:
        return Response(get_user_data(request.user))
    except Exception as e:
        return Response({"error": str(e)}, status=400)
