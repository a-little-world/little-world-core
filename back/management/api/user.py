import urllib.parse
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.dispatch import receiver
from django.http import HttpResponseRedirect
from django.urls import path
from django.utils import timezone
from django_rest_passwordreset.signals import reset_password_token_created
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from ipware import get_client_ip as get_ip
from rest_framework import authentication, permissions, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from tracking import utils
from tracking.models import Event
from translations import get_translation

from management.authentication import NativeOnlyJWTAuthentication, silent
from management.controller import UserNotFoundErr, delete_user, get_user_by_email, get_user_by_uuid
from management.models.banner import Banner, BannerSerializer
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from management.models.profile import SelfProfileSerializer
from management.models.state import FrontendStatusSerializer, State
from management.permissions import ManagementPermission
from management.tasks import send_email_background

"""
The public /user api's

`user/get` and `user/list` are only available for admins (`admin/` prefix) see api.admin
"""


def verify_email_link(auth_data):
    try:
        _data = State.decode_email_auth_code_b64(auth_data)
        usr = get_user_by_uuid(_data["u"])
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
    authentication_classes = [SessionAuthentication, NativeOnlyJWTAuthentication]

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
        except (ValueError, TypeError):
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
    lookup: str  # lookup: uuid | email | id
    token: str  # auto login token
    n: Optional[str] = None  # next page


class AutoLoginSerializer(serializers.Serializer):
    u = serializers.CharField(required=True)
    lookup = serializers.CharField(required=True)
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

        user_mail = login_data.email.lower()
        usr = authenticate(username=user_mail, password=login_data.password)

        if usr is not None:
            if usr.is_staff:  # type: ignore
                # pylint thinks this is a AbsUsr but we have overwritten it models.user.User
                return Response(get_translation("api.login_failed_staff"), status=status.HTTP_400_BAD_REQUEST)

            if usr.has_perm(ManagementPermission.MATCHING_USER):
                # send security notification: Matching user new login
                ip, routable = get_ip(request)
                security_notification = f"Matching user {usr.email} logged in from {ip}"
                from management.tasks import slack_notify_security_channel_async

                slack_notify_security_channel_async.delay(security_notification)

            # token_auth is a query parameter that determines whether to return a token or create a session
            token_auth = request.query_params.get("token_auth", False)
            if token_auth:
                # Legacy token auth - now deprecated in favor of native challenge-response
                return Response(
                    "Token auth deprecated. Use /api/user/native-login for native apps",
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:
                login(request, usr)
                return Response(get_user_data(request.user))
        else:
            if user_mail in [settings.MANAGEMENT_USER_MAIL, settings.MATCHING_USER_MAIL]:
                # send security notification: Admin / Matching user failed login attepts are logged!
                ip, routable = get_ip(request)
                security_notification = f"FAILED login attempt for matching/staff user {user_mail} from {ip}"
                from management.tasks import slack_notify_security_channel_async

                slack_notify_security_channel_async.delay(security_notification)
            return Response(get_translation("api.login_failed"), status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(request=AutoLoginSerializer(many=False))
    def get(self, request):
        """
        Allowes to authenticate users using the extra auth token
        TODO: @tbscode depricate
        """
        return Response("Auto-login API is deprecated and disabled", status=status.HTTP_410_GONE)


class LogoutApi(APIView):
    authentication_classes = [
        authentication.SessionAuthentication,
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
    authentication_classes = [authentication.SessionAuthentication, NativeOnlyJWTAuthentication]
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
                        "email":  # future: throttle this APIView to pre-vent email enumeration?
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
    authentication_classes = [
        authentication.SessionAuthentication,
        NativeOnlyJWTAuthentication,
    ]
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
            for match_uuid in params.matches:
                partner = get_user_by_uuid(match_uuid)

                from management.models.matches import Match

                match = Match.get_match(request.user, partner)
                assert match.exists()
                match = match.first()
                assert match is not None
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
    authentication_classes = [authentication.SessionAuthentication, NativeOnlyJWTAuthentication]
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
        if params.state_slug == State.SearchingStateChoices.SEARCHING:
            # Now check if the user has receive a matching before
            if settings.ENABLE_AUTO_EMAILS__U081_U082_U083_U084:
                if request.user.state.has_received_first_match and (not request.user.state.auto_emails_u081_send):
                    # send searching again email once
                    emulated_send = bool(settings.DJANGO_TESTING) or bool(
                        settings.EMULATE_AUTO_EMAILS__U081_U082_U083_U084
                    )
                    send_email_background.delay(
                        "automatic-emails-u081", user_id=request.user.id, emulated_send=emulated_send
                    )
                    request.user.state.auto_emails_u081_send = True
                    request.user.state.save()

        if (params.state_slug == State.SearchingStateChoices.SEARCHING) and request.user.state.unresponsive:
            # If the user was manaully set to 'unresponsive' he can self remove this flag by searching him-self again
            request.user.state.unresponsive = False
            request.user.state.save()

        return Response(get_translation("api.user_update_searching_state_state_successfully_changed"))


class UnmatchSelfSerializer(serializers.Serializer):
    other_user_uuid = serializers.CharField(required=True)
    reason = serializers.CharField(required=True)

    def create(self, validated_data):
        return validated_data


@login_required
@api_view(["POST"])
def resend_verification_mail(request):
    request.user.send_email("verify-email")
    return Response("Resend verification mail")


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, *args, **kwargs):
    """
    Handles password reset tokens
    This is automaticly called fron djang-rest-password reset when the /api/user/resetpw is called
    """
    # This is the url of our password reset view
    # We also pass the reset token to the view so it can be used to change the password
    usr_uuid = reset_password_token.user.uuid
    reset_password_url = f"{settings.BASE_URL}/set_password/{usr_uuid}/{reset_password_token.key}"

    reset_password_token.user.send_email("reset-password", context={"reset_password_url": reset_password_url})


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
    assert not request.user.has_perm(ManagementPermission.MATCHING_USER)

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
            {"email": str(user.email), "uuid": str(user.uuid), "bookingcode": str(user.state.prematch_booking_code)}
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

    has_random_calls_access = ("herrduenschnlate+" in str(user.email)) or user.has_perm(
        ManagementPermission.USE_RANDOM_CALLS
    )

    # Self-onboarding progress as a fraction in [0, 1] based on the ordered step list.
    onboarding_rank = get_rank_from_stored_self_onboarding_value(user_state.self_onboarding_step_id)
    self_onboarding_progress = 0.0
    if SELF_ONBOARDING_COMPLETED_RANK > 0:
        self_onboarding_progress = max(0.0, min(1.0, onboarding_rank / float(SELF_ONBOARDING_COMPLETED_RANK)))

    return {
        "id": str(user.uuid),
        "banner": banner,
        "status": FrontendStatusSerializer(user_state).data,
        "isSupport": user.has_perm(ManagementPermission.MATCHING_USER) or user.is_staff,
        "isSearching": user_state.searching_state == State.SearchingStateChoices.SEARCHING,
        "email": user.email,
        "hasRandomCallsAccess": has_random_calls_access,
        "preMatchingAppointment": pre_match_appointent,
        "preMatchingCallJoinLink": pre_call_join_link,
        "calComAppointmentLink": cal_data_link,
        "hadPreMatchingCall": user_state.had_prematching_call,
        "selfOnboardingCompleted": user_state.self_onboarding_completed,
        "selfOnboardingStepId": user_state.self_onboarding_step_id or "",
        "selfOnboardingProgress": self_onboarding_progress,
        "isOnboarded": user_state.is_onboarded,
        "selfOnboardingStarted": user_state.self_onboarding_started,
        "forceMatchEligible": user_state.force_match_eligible,
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


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([silent(SessionAuthentication), silent(NativeOnlyJWTAuthentication)])
def is_authenticated(request):
    """
    Returns whether the user is authenticated.
    """
    return Response(request.user.is_authenticated)


SELF_ONBOARDING_STEP_ORDER = (
    "self_onboarding_c1_q_1",
    "self_onboarding_c2_q_1",
    "self_onboarding_c3_q_1",
)
SELF_ONBOARDING_STEP_TO_RANK = {step_id: idx + 1 for idx, step_id in enumerate(SELF_ONBOARDING_STEP_ORDER)}
SELF_ONBOARDING_COMPLETED_RANK = len(SELF_ONBOARDING_STEP_ORDER)


def get_rank_from_stored_self_onboarding_value(stored: str | None) -> int:
    """Rank from stored canonical step id only; unknown or empty values are treated as not started."""
    if not stored:
        return 0
    s = str(stored).strip()
    if not s:
        return 0
    return SELF_ONBOARDING_STEP_TO_RANK.get(s, 0)


def get_self_onboarding_step_rank(request) -> int | None:
    step_id = request.query_params.get("self_onboarding_step_id")
    if not step_id:
        return None
    return SELF_ONBOARDING_STEP_TO_RANK.get(step_id)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def self_onboarding_update(request):
    step_id = request.query_params.get("self_onboarding_step_id")
    self_onboarding_step_rank = get_self_onboarding_step_rank(request)
    if self_onboarding_step_rank is None or not step_id:
        return Response(
            {
                "completed": False,
                "message": "Invalid self onboarding step id",
            },
            status=400,
        )

    user = request.user
    completed = False

    current_rank = get_rank_from_stored_self_onboarding_value(user.state.self_onboarding_step_id)
    if self_onboarding_step_rank > current_rank:
        user.state.self_onboarding_step_id = step_id

    if self_onboarding_step_rank > 0:
        user.state.self_onboarding_started = True

    if self_onboarding_step_rank >= SELF_ONBOARDING_COMPLETED_RANK:
        user.state.self_onboarding_completed_at = timezone.now()
        user.state.self_onboarding_completed = True
        user.state.is_onboarded = True
        user.grant_permission(ManagementPermission.USE_RANDOM_CALLS)
        user.state.searching_state = State.SearchingStateChoices.SEARCHING
        send_email_background.delay("automatic-emails-u071", user_id=user.id)
        user.state.attended_auto_email_u071_send = True
        user.state.attended_auto_email_u071_send_at = timezone.now()
        completed = True

    user.state.save()
    return Response(
        {
            "completed": completed,
            "message": "Self onboarding updated successfully",
        }
    )


api_urls = [
    path("api/user", user_profile, name="user_profile_api"),
    path("api/user/authenticated", is_authenticated, name="user_is_authenticated_api"),
    path("api/user/confirm_match/", ConfirmMatchesApi.as_view()),
    path(
        "api/user/search_state/<str:state_slug>",
        UpdateSearchingStateApi.as_view(),
    ),
    path("api/user/login/", LoginApi.as_view()),
    path("api/user/logout/", LogoutApi.as_view()),
    path("api/user/checkpw/", CheckPasswordApi.as_view()),
    path("api/user/changepw/", ChangePasswordApi.as_view()),
    path("api/user/change_email/", ChangeEmailApi.as_view()),
    path(
        "api/user/verify/email/<str:auth_data>",
        VerifyEmail.as_view(),
    ),
    path("api/user/verify/email_resend/", resend_verification_mail),
    path(
        "user/still_active/",
        still_active_callback,
        name="still_active_callback",
    ),
    path(
        "api/user/delete_account/",
        delete_account,
        name="delete_account_api",
    ),
    path(
        "api/user/self_onboarding/update/",
        self_onboarding_update,
        name="self_onboarding_update_api",
    ),
]
