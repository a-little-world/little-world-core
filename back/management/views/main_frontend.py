from management.api.user_data import frontend_data
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.decorators import api_view
from back.utils import CoolerJson
from django.utils.translation import pgettext_lazy
from management.views.cookie_banner_frontend import get_cookie_banner_template_data
from django.utils import translation
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

class MainFrontendRouter(View):
    
    # react frontend public paths
    PUBLIC_PATHS = [
        "login", 
        "sign-up", 
        "forgot-password", 
        "reset-password",
    ]

    def get(self, request, path="", **kwargs):
        
        # normalize path, no trailing slash
        if path.endswith("/"):
            path = path[:-1]

        login_url_redirect = ('https://home.little-world.com/' if settings.IS_PROD else '/login') if (not settings.USE_LANDINGPAGE_REDIRECT) else settings.LANDINGPAGE_REDIRECT_URL
        
        if not request.user.is_authenticated:
            if path in self.PUBLIC_PATHS:
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

                cookie_context = get_cookie_banner_template_data(request)
                return render(request, "main_frontend_public.html", {
                        "data": json.dumps(data, cls=CoolerJson), **cookie_context})
            if path == "":
                # the root path is generally redirected to `little-world.com` in production ( otherwise to an app intern landing page )
                return redirect(login_url_redirect)
            if not path.startswith("/"):
                path = f"/{path}"
            return redirect(f"{login_url_redirect}?next={path}")
        
        # authenticated users
        
        if (not request.user.state.is_email_verified()) and (not path.startswith("app/verify-email")):
            return redirect("/app/verify-email/")
        
        if request.user.state.is_email_verified() and ((not request.user.state.is_user_form_filled()) and (not path.startswith("app/user-form"))):
            return redirect("/app/user-form/")

        if request.user.state.is_email_verified() and request.user.state.is_user_form_filled() and (not path.startswith("app")):
            return redirect("/app/")


        extra_template_data = {}
        with translation.override("tag"):
            data = frontend_data(request.user)
        extra_template_data["sentry_user_id"] = request.user.hash

        return render(request, "main_frontend_public.html", {"data": json.dumps(data, cls=CoolerJson), **extra_template_data})

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
        "linkTo": linkTo
    }
    
    if confirm_mode:
        raise NotImplementedError("confirm mode not yet implemented")
    
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
