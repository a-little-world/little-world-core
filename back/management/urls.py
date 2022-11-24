from . import views, api
from django.urls import path, re_path
from django.contrib import admin
from django.conf import settings
from . import views
from back.utils import _api_url
from django.conf.urls import include
from django.views.generic.base import RedirectView
from rest_framework import routers
from django.contrib.auth import views as auth_views
from .views.user_form_frontend import (
    login,
    register,
    forgot_password,
    set_password_reset,
    subsection_of_user_form,
    email_verification,
    email_change,
    email_verification_sucess,
    email_verification_fail,
    error,
    user_form
)

from rest_framework.routers import DefaultRouter
from django_rest_passwordreset.views import ResetPasswordValidateTokenViewSet, ResetPasswordConfirmViewSet, \
    ResetPasswordRequestTokenViewSet

router = DefaultRouter()
router.register(  # TODO: we might even wan't to exclude this api
    r'api/user/resetpw/validate',
    ResetPasswordValidateTokenViewSet,
    basename='reset-password-validate'
)
router.register(
    r'api/user/resetpw/confirm',
    ResetPasswordConfirmViewSet,
    basename='reset-password-confirm'
)
router.register(
    r'api/user/resetpw',
    ResetPasswordRequestTokenViewSet,
    basename='reset-password-request'
)


api_routes = [
    # User
    path(_api_url('user_data'), api.user_data.UserData.as_view()),

    path(_api_url('trans/<str:lang>'), api.trans.TranslationsGet.as_view()),

    path(_api_url('register'), api.register.Register.as_view()),
    path(_api_url('user'), api.user_data.SelfInfo.as_view()),
    path(_api_url('user/login'), api.user.LoginApi.as_view()),
    path(_api_url('user/checkpw'), api.user.CheckPasswordApi.as_view()),
    path(_api_url('profile'),
         api.profile.ProfileViewSet.as_view({"post": "partial_update", "get": "_get"})),

    path(_api_url('notification'),
         api.notify.NotificationGetApi.as_view()),
    path(_api_url('notification/<str:action>', end_slash=False),
         api.notify.NotificationActionApi.as_view()),


    # e.g.: /user/verify/email/Base64{d=email&u=hash&k=pin:hash}
    path(_api_url('user/verify/email/<str:auth_data>', end_slash=False),
         api.user.VerifyEmail.as_view()),

    # Admin
    path(_api_url('user/get', admin=True), api.admin.GetUser.as_view()),
    path(_api_url('user/list', admin=True), api.admin.UserList.as_view()),

    #    path(_api_url('user/match', admin=True), api.admin.MakeMatch.as_view()),
    #    path(_api_url('user/suggest_match', admin=True),
    #         api.admin.MatchingSuggestion.as_view()),
    *router.urls
]

view_routes = [
    path("", RedirectView.as_view(  # Redirect all requests to "/" to "/app/" per default
         url=f"app/", permanent=True), name="frontend_redirect"),

    path("register/", register, name="register"),
    path("password_reset/", forgot_password, name="password_reset"),
    path("set_password/<str:usr_hash>/<str:token>",
         set_password_reset, name="set_password_reset"),

    path("login/", login, name="login"),

    path("formpage/", subsection_of_user_form, name="formpage"),

    path('mailverify/', email_verification, name="email_verification"),
    path('mailchange/', email_change, name="email_change"),
    path('mailverify/sucess/', email_verification_sucess,
         name="email_verification_sucess"),
    path('mailverify/fail/', email_verification_fail,
         name="email_verification_fail"),

    path('error/', error, name="error"),

    # The user form ( does its own routing )
    path(f"form/", user_form, name="user_form"),
    re_path(fr'^form/(?P<path>.*)$', user_form),

    # The main frontend ( does its own routing )
    path('app/', views.MainFrontendView.as_view(), name="main_frontend"),
    re_path(fr'^app/(?P<path>.*)$',
            views.MainFrontendView.as_view(), name="main_frontend_w_path"),

]

urlpatterns = [
    *view_routes,
    *api_routes,
]
