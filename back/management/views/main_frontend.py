import json
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings
from django.shortcuts import redirect, render
from django.utils import translation
from django.views import View
from rest_framework import serializers, status
from rest_framework.request import Request
from translations import get_translation

from back.utils import CoolerJson, transform_add_options_serializer
from management.controller import get_base_management_user
from management.models.profile import SelfProfileSerializer
from management.views.cookie_banner_frontend import get_cookie_banner_template_data
from management.api.user import get_user_data
from management.models.short_links import ShortLink

# The following two are redundant with api.admin.UserListParams, api.admin.UserListApiSerializer
# But that is desired I wan't to always handle admin logic separately this might come in handy in the future


@dataclass
class MainFrontendParams:
    filters: "list[str]" = field(default_factory=list)
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
    PUBLIC_PATHS = ["login", "sign-up", "forgot-password", "reset-password", "email-preferences"]

    LOGGED_IN_NO_REDIRECT_PATHS = [
        "app",
        "email-preferences",
    ]

    def get(self, request, path="", **kwargs):
        # normalize path, no trailing slash
        if path.endswith("/"):
            path = path[:-1]


        login_url_redirect = (
            ("https://home.little-world.com/" if settings.IS_PROD else "/login")
            if (not settings.USE_LANDINGPAGE_REDIRECT)
            else settings.LANDINGPAGE_REDIRECT_URL
        )
        ProfileWOptions = transform_add_options_serializer(SelfProfileSerializer)

        if not request.user.is_authenticated:
            if any([path.startswith(p) for p in self.PUBLIC_PATHS]):
                cookie_context = get_cookie_banner_template_data(request)

                return render(
                    request, "main_frontend.html", {
                        "user": json.dumps({}),
                        "api_options": json.dumps({
                            "profile": ProfileWOptions(get_base_management_user().profile).data["options"],
                        }),
                        **cookie_context
                    }
                )


            root_short_links = ShortLink.objects.filter(register_at_app_root=True, tag=path)
            if root_short_links.exists():
                return redirect(f"/links/{root_short_links.first().tag}/")


            if path == "":
                # the root path is generally redirected to `little-world.com` in production ( otherwise to an app intern landing page )
                return redirect(login_url_redirect)
            if not path.startswith("/"):
                path = f"/{path}"
            return redirect(f"{login_url_redirect}?next={path}")

        # authenticated users

        if (not request.user.state.is_email_verified()) and (not path.startswith("app/verify-email")):
            return redirect("/app/verify-email/")

        if request.user.state.is_email_verified() and (
            (not request.user.state.is_user_form_filled()) and path.startswith("app/verify-email")
        ):
            return redirect("/app/user-form/")

        if request.user.state.is_email_verified() and (
            (not request.user.state.is_user_form_filled()) and (not path.startswith("app/user-form"))
        ):
            return redirect("/app/user-form/")

        if (
            request.user.state.is_email_verified()
            and request.user.state.is_user_form_filled()
            and (not any([path.startswith(p) for p in self.LOGGED_IN_NO_REDIRECT_PATHS]))
        ):
            return redirect("/app/")

        extra_template_data = {}
        with translation.override("tag"):
            user_data = get_user_data(request.user)
        extra_template_data["sentry_user_id"] = request.user.hash

        return render(
            request, "main_frontend.html", {
                "user": json.dumps(user_data, cls=CoolerJson),
                "api_options": json.dumps({
                    "profile": ProfileWOptions(request.user.profile).data["options"],
                }),
                **extra_template_data
            }
        )

def info_card(
    request,
    confirm_mode=False,
    title="",
    content="",
    confirmText="",
    rejectText="",
    linkText="",
    linkTo="",
    status_code=status.HTTP_200_OK,
):
    # cast rest_framework request to django request

    data = {"title": title, "content": content, "linkText": linkText, "linkTo": linkTo}

    if confirm_mode:
        raise NotImplementedError("confirm mode not yet implemented")

    if isinstance(request, Request):
        request = request._request

    # info view relies on frontend translations per default
    with translation.override("tag"):
        return render(request, "info_card.html", {"data": json.dumps(data, cls=CoolerJson)}, status=status_code)


def debug_info_card(request):
    return info_card(
        request, title="Debug Info Card", content="This is a debug info card", linkText="Go back to app", linkTo="/app/"
    )


def email_verification_link(request, **kwargs):
    from management.api.user import verify_email_link

    if "auth_data" not in kwargs:
        raise serializers.ValidationError({"auth_data": get_translation("errors.missing_email_auth_data_get_frontend")})

    if verify_email_link(kwargs["auth_data"]):
        return info_card(
            request,
            title=get_translation("info_view.email_verification_link_success.title"),
            content=get_translation("info_view.email_verification_link_success.content"),
            linkText=get_translation("info_view.email_verification_link_success.linkText"),
            linkTo="/app/",
        )
    else:
        return info_card(
            request,
            title=get_translation("info_view.email_verification_link_failure.title"),
            content=get_translation("info_view.email_verification_link_failure.content"),
            linkText=get_translation("info_view.email_verification_link_failure.linkText"),
            linkTo="/app/",
        )


def handler404(request, exception=None):
    return info_card(
        request,
        title=get_translation("info_view.404.title"),
        content=get_translation("info_view.404.content"),
        linkText=get_translation("info_view.404.linkText"),
        linkTo="/app/",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def handler500(request, exception=None):
    return info_card(
        request,
        title=get_translation("info_view.500.title"),
        content=get_translation("info_view.500.content"),
        linkText=get_translation("info_view.500.linkText"),
        linkTo="/app/",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
    # TODO: this url should only be opened with a valid token, otherwise this should error!
    from django_rest_passwordreset.serializers import ResetTokenSerializer

    serializer = SetPasswordResetSerializer(
        data={"usr_hash": kwargs.get("usr_hash", None), "token": kwargs.get("token", None)}
    )  # type: ignore

    serializer.is_valid(raise_exception=True)
    params = serializer.save()

    try:
        token_serializer = ResetTokenSerializer(
            data={
                "token": params.token,
            }
        )

        token_serializer.is_valid(raise_exception=True)
    except Exception:
        return info_card(
            request,
            title=get_translation("info_view.set_password_reset_failure.title"),
            content=get_translation("info_view.set_password_reset_failure.content"),
            linkText=get_translation("info_view.set_password_reset_failure.linkText"),
            linkTo="/app/",
        )

    # otherwise redirect to the change password frontend page
    return redirect(f"/reset-password/{params.usr_hash}/{params.token}/")
