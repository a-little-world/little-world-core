from . import views, api
from django.urls import path, re_path
from django.contrib import admin
from django.conf import settings
from . import views
from back.utils import _api_url
from django.conf.urls import include
from rest_framework import routers
from django.contrib.auth import views as auth_views
from .views.user_form_frontend import (
    login,
    register,
    subsection_of_user_form,
    email_verification,
    email_change,
    email_verification_sucess,
    email_verification_fail,
    error
)


router = routers.SimpleRouter()
# Register possible viewsets here ... TODO
api_routes = [
    # User
    path(_api_url('user_data'), api.user_data.UserData.as_view()),

    path(_api_url('register'), api.register.Register.as_view()),
    path(_api_url('user'), api.user_data.SelfInfo.as_view()),
    path(_api_url('user/login'), api.user.LoginApi.as_view()),
    path(_api_url('profile'),
         api.profile.ProfileViewSet.as_view({"post": "partial_update", "get": "_get"})),

    path(_api_url('notification'),
         api.notify.NotificationGetApi.as_view()),
    path(_api_url('notification/<str:action>', end_slash=False),
         api.notify.NotificationActionApi.as_view()),


    # e.g.: /user/verify/email/Base64{d=email&u=hash&k=pin:hash}
    path(_api_url('user/verify/email/<str:auth_data>'),  # TODO create verify email api
         api.user.VerifyEmail.as_view()),

    # Admin
    path(_api_url('user/get', admin=True), api.admin.GetUser.as_view()),
    path(_api_url('user/list', admin=True), api.admin.UserList.as_view()),
    #    path(_api_url('user/match', admin=True), api.admin.MakeMatch.as_view()),
    #    path(_api_url('user/suggest_match', admin=True),
    #         api.admin.MatchingSuggestion.as_view()),
    *router.urls
]

extra_auth_views = [
    path('accounts/reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='registration/password_reset_confirm_custom.html'
         ),
         name='password_reset_confirm'),
    path('anAdminPathTh3yS4y/', admin.site.urls),
    path('accounts/password_reset/',
         auth_views.PasswordResetView.as_view(
             html_email_template_name='email/pw_reset.html'
         ),
         name='password_reset'
         ),
    # TODO: do we really need to include them all?:
    path('accounts/', include("django.contrib.auth.urls")),
]

view_routes = [
    path("register", register, name="register"),

    path("login", login, name="login"),

    path("formpage", subsection_of_user_form, name="formpage"),

    path('mailverify/', email_verification, name="email_verification"),
    path('mailchange/', email_change, name="email_change"),
    path('mailverify/sucess/', email_verification_sucess,
         name="email_verification_sucess"),
    path('mailverify/fail/', email_verification_fail,
         name="email_verification_fail"),

    path('error/', error, name="error"),


    path('app/', views.MainFrontendView.as_view(), name="main_frontend"),
    re_path(fr'^app/(?P<path>.*)$',
            views.MainFrontendView.as_view(), name="main_frontend_w_path"),

]

urlpatterns = [
    *api_routes,
    *view_routes,
    *extra_auth_views
]
