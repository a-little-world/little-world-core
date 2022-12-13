from .cookie_banner_frontend import get_cookie_banner_template_data
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
from rest_framework import serializers
from dataclasses import dataclass
from django.urls import reverse
import json


def _render_user_form_app(request, app_name="", use_cookie_banner=False, **kwargs):
    """
    This renders any user form app this is always handles by running render_app()
    You can render a specific subset of the app by passing 'byName'
    see user_from_fromtend/src/index.tsx for more info
    set app_name = "" to render the main userform
    """
    context = {"app_name": app_name}
    if use_cookie_banner:
        context.update(get_cookie_banner_template_data(request))
    context.update({"kwargs": json.dumps(kwargs)
                   if kwargs else {}})  # type: ignore
    return render(request, "user_form_frontend.html", context)


# Acessible open page: register, login:

def login(request):
    if request.user.is_authenticated:
        return redirect(reverse("management:main_frontend", kwargs={}))
    return _render_user_form_app(request, "login", use_cookie_banner=True)


def forgot_password(request):
    return _render_user_form_app(request, "resetpw", use_cookie_banner=True)


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
    serializer = SetPasswordResetSerializer(data={
        "usr_hash": kwargs.get("usr_hash", None),
        "token": kwargs.get("token", None)
    })  # type: ignore
    # TODO: handle gracefully and show error screen:
    serializer.is_valid(raise_exception=True)
    params = serializer.save()

    # Now validate the token, if its valid maybe update using django_rest_password reset
    # TODO: if token invalid redirect to token ivalid page!

    return _render_user_form_app(
        request, "setpw", use_cookie_banner=True, usr_hash=params.usr_hash, token=params.token)


def password_set_success(request):
    return _render_user_form_app(request, "passwordset", use_cookie_banner=True)


def password_reset_mail_send(request):
    return _render_user_form_app(request, "mailsend", use_cookie_banner=True)


def register(request):
    return _render_user_form_app(request, "register", use_cookie_banner=True)

# Inacessible setup pages ( only for loggedin users )


@login_required
def email_verification(request):
    if request.user.state.is_email_verified():
        return redirect(reverse("management:user_form", kwargs={}))
    return _render_user_form_app(request, "verifymail", use_cookie_banner=True, email=request.user.email)


@login_required
def email_change(request):
    return _render_user_form_app(request, "changemail", use_cookie_banner=True)


@login_required
def email_verification_sucess(request):
    return _render_user_form_app(request, "mailverificationsucess")


@login_required
def email_verification_fail(request):
    return _render_user_form_app(request, "mailverificationfail")


def error(request):
    return _render_user_form_app(request, "error")


@login_required
def subsection_of_user_form(request):
    """ This uses some js magic in the user_form app to render only one page of the user form """
    pages = request.GET.get("pages", None)
    # TODO: we might wan't to filter allowed pages,
    # since some pages could be used to delte old userform data,
    # making it unfilled again ( But they could to that anyways with the api directly )
    assert pages, "pages need to provided for this view"
    return _render_user_form_app(request, "oneformpageonly", use_cookie_banner=False, pages=pages)


@ login_required
def user_form(request, path=None):
    """
    Renders the main user form app, this data is used for matching the users
    this app is allowed to reserve all front/* paths
    """
    return _render_user_form_app(request, localdev=settings.IS_DEV)
