from management.api.user_data import get_full_frontend_data, frontend_data
from pdoc import cli
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.decorators import api_view
from back.utils import CoolerJson
from django.utils.translation import pgettext_lazy
from django.conf import settings
import json
from dataclasses import dataclass, field
from django.shortcuts import render, redirect
from django.urls import reverse
from rest_framework.request import Request
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework import serializers
from django.views import View
from rest_framework.response import Response
from typing import List, Optional
from tracking import utils
from management.models.profile import SelfProfileSerializer
from tracking.models import Event
from management.controller import get_base_management_user
from back.utils import transform_add_options_serializer


# The following two are redundant with api.admin.UserListParams, api.admin.UserListApiSerializer
# But that is desired I wan't to always handle admin logic seperately this might come in handy in the future

@dataclass
class MainFrontendParams:
    filters: 'list[str]' = field(default_factory=list)
    paginate_by: int = 50
    order_by: Optional[str] = None  # Use default order per default
    page: int = 1


class MainFrontendParamsSerializer(serializers.Serializer):
    # All these parameters are only allowed for admins!
    filters = serializers.ListField(required=False)
    paginate_by = serializers.IntegerField(required=False)
    page = serializers.IntegerField(required=False)
    order_by = serializers.CharField(required=False)

    def create(self, validated_data):
        return MainFrontendParams(**validated_data)

class PublicMainFrontendView(View):

    @utils.track_event(name=_("Render User Form"), event_type=Event.EventTypeChoices.REQUEST, tags=["frontend"])
    def get(self, request, path, **kwargs):
        
        if request.user.is_authenticated and ((not request.user.state.is_email_verified()) and (not path.startswith("verify-email"))):
            return redirect("/verify-email/")
        
        if request.user.is_authenticated and request.user.state.is_email_verified() and ((not request.user.state.is_user_form_filled()) and (not path.startswith("app/user-form"))):
            return redirect("/app/user-form/")

        if request.user.is_authenticated and (request.user.state.is_email_verified() and request.user.state.is_user_form_filled()):
            return redirect("/app/")


        if request.user.is_authenticated:
            data = frontend_data(request.user)
        else:
            # TODO: we need a better way to extract the options!
            ProfileWOptions = transform_add_options_serializer(SelfProfileSerializer)
            user_profile = get_base_management_user().profile
            profile_data = ProfileWOptions(user_profile).data
            profile_options = profile_data["options"]
            data = {
                "apiOptions": {
                    "profile": profile_options,
                },
            }
            
        from management.views.cookie_banner_frontend import get_cookie_banner_template_data
        cookie_context = get_cookie_banner_template_data(request)

        return render(request, "main_frontend_public.html", {"data": json.dumps(data, cls=CoolerJson), **cookie_context})

class MainFrontendView(LoginRequiredMixin, View):
    login_url = ('https://home.little-world.com/' if settings.IS_PROD else '/login') if (not settings.USE_LANDINGPAGE_REDIRECT) else settings.LANDINGPAGE_REDIRECT_URL
    redirect_field_name = 'next'

    @utils.track_event(name=_("Render User Form"), event_type=Event.EventTypeChoices.REQUEST, tags=["frontend"])
    def get(self, request, path="app/", **kwargs):
        """
        Entrypoint to the main frontend react app.
        1. check if email verified, if not redirect to views.form.email_verification
        2. check if user form filled, if not redirect to views.from.user_form

        TODO this **will** change, 
        at some point we will allow to use the main app even without having your email verified
        """
        
        if not path.startswith("app/"):
            path = "app/" + path

        # This is a regular django view,
        # but since we still wan't to use serialization from DRF
        # We will wrap the 'request' into a DRF.request
        # This gives us json parsed .data and .query_set options
        drf_request = Request(request=request)

        if not request.user.is_staff and len(drf_request.query_params) != 0:
            # TODO: this check doesn't seems to work
            return Response(_('Query param usage on main view only allowed for admins!'), status=status.HTTP_403_FORBIDDEN)

        serializer = MainFrontendParamsSerializer(
            data=drf_request.query_params)  # type: ignore

        if not serializer.is_valid():
            # Since this is a regular django view we have to return the erros manually
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        params = serializer.save()
        print("PRMS: " + str(params))

        
        if request.user.is_authenticated and ((not request.user.state.is_email_verified()) and (not path.startswith("verify-email"))):
            return redirect("/verify-email/")
        
        if request.user.is_authenticated and ((not request.user.state.is_user_form_filled()) and (not path.startswith("app/user-form"))):
            return redirect("/app/user-form/")

        _kwargs = params.__dict__
        _kwargs.pop("filters")  # TODO: they are not yet supported
        _kwargs.pop("order_by")  # TODO: they are not yet supported
        from django.utils import translation

        # we want this view to pass tags by default,
        # the frontend also receives all api translations!
        # This way it can switch the language without reloading
        with translation.override("tag"):
            data = frontend_data(request.user)
        return render(request, "main_frontend.html", {"data": json.dumps(data, cls=CoolerJson)})
    
def info_card(
        request, 
        confirm_mode=False,
        title="",
        content="",
        # TODO: confirm / reject logic not yet implemented!
        confirmText="",
        rejectText="",
        linkText="",
        linkTo="",
        status_code=status.HTTP_200_OK
    ):
    
    # cast rest_framework request to django request
    
    data = {
        "title": title,
        "content": content,
        "linkText": linkText,
        "linkTo": "https://little-world.com/"
    }
    
    # TODO confirm_mode = True not yet implemented
    if isinstance(request, Request):
        request = request._request

    from django.utils import translation
    # info view relies on frontend translations per default
    with translation.override("tag"):
        return render(request, "info_card.html", {"data": 
                       json.dumps(data, cls=CoolerJson)}, status=status_code)
        
def email_verification_link(request, **kwargs):
    from management.api.user import verify_email_link

    if not 'auth_data' in kwargs:
        raise serializers.ValidationError(
            {"auth_data": pgettext_lazy("email.verify-auth-data-missing-get-frontend",
                                        "Email authentication data missing")})

    if verify_email_link(kwargs['auth_data']):
        return info_card(
            request,
            title=pgettext_lazy(
                "info-view.email-verification-link.title", 
                "Email verification successful"),
            content=pgettext_lazy(
                "info-view.email-verification-link.content", 
                "Your email has been verified successfully"),
            linkText=pgettext_lazy(
                "info-view.email-verification-link.linkText", 
                "Back to home"),
            linkTo="/app/")
    else:
        return info_card(
            request,
            title=pgettext_lazy(
                "info-view.email-verification-link.title", 
                "Email verification failed"),
            content=pgettext_lazy(
                "info-view.email-verification-link.content", 
                "Your email verification failed"),
            linkText=pgettext_lazy(
                "info-view.email-verification-link.linkText", 
                "Back to home"),
            linkTo="/app/")

def handler404(request, exception=None):
    return info_card(
        request,
        title=pgettext_lazy(
            "info-view.404.title", 
            "Page not found"),
        content=pgettext_lazy(
            "info-view.404.content", 
            "The page you are looking for does not exist"),
        linkText=pgettext_lazy(
            "info-view.404.linkText", 
            "Back to home"),
        linkTo="/app/",
        status_code=status.HTTP_404_NOT_FOUND
    )

def handler500(request, exception=None):
    return info_card(
        request,
        title=pgettext_lazy(
            "info-view.500.title", 
            "Internal server error"),
        content=pgettext_lazy(
            "info-view.500.content", 
            "An internal server error occured\nIf you think this is a bug please contact us"),
        linkText=pgettext_lazy(
            "info-view.500.linkText",
            "Back to home"),
        linkTo="/app/",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    


@dataclass
class SetPasswordResetParams:
    usr_hash: str
    token: str


class SetPasswordResetSerializer(serializers.Serializer):
    usr_hash = serializers.CharField(required=True)
    token = serializers.CharField(required=True)

    def create(self, validated_data):
        return SetPasswordResetParams(**validated_data)  # type: ignore


def set_password_reset(request, **kwargs):
    # TODO: this url should only be opened with a valid topen, otherwise this should error!
    from django_rest_passwordreset.serializers import ResetTokenSerializer

    serializer = SetPasswordResetSerializer(data={
        "usr_hash": kwargs.get("usr_hash", None),
        "token": kwargs.get("token", None)
    })  # type: ignore

    serializer.is_valid(raise_exception=True)
    params = serializer.save()
        
    try:
        token_serializer = ResetTokenSerializer(data={
            "token": params.token,
        })
        
        token_serializer.is_valid(raise_exception=True)
    except Exception as e:
        return info_card(
            request,
            title=pgettext_lazy(
                "info-view.set-password-reset.title", 
                "Password reset failed"),
            content=pgettext_lazy(
                "info-view.set-password-reset.content", 
                "Token is invalid"),
            linkText=pgettext_lazy(
                "info-view.set-password-reset.linkText", 
                "Back to home"),
            linkTo="/app/"
        )
        
    # otherwise redirect to the change password frontend page
    return redirect(f"/reset-password/{params.usr_hash}/{params.token}/")
