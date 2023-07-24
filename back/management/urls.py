from management import api
from django.urls import path, re_path
from django.contrib import admin
from django.conf import settings
from management import views
from back.utils import _api_url
from django.conf.urls import include
from django.views.generic.base import RedirectView
from rest_framework import routers
from django.contrib.auth import views as auth_views
from management.views.user_form import (
    user_form_v2
)
from management.views.user_form_frontend import (
    login,
    register,
    forgot_password,
    set_password_reset,
    password_reset_mail_send,
    subsection_of_user_form,
    email_verification,
    email_change,
    email_verification_sucess,
    email_verification_fail,
    password_set_success,
    error,
    email_verification_link_screen,
    user_form
)
from management.views.admin_panel_frontend import admin_panel, stats_panel, graph_panel, fetch_graph, user_list_frontend, fetch_list
from management.views.admin_panel_v2 import admin_panel_v2, root_user_viewset, advanced_user_listing

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
    path(_api_url('user_data_v2'), api.user_data.user_data_v2),

    path(_api_url('trans/<str:lang>'), api.trans.TranslationsGet.as_view()),


    path(_api_url('community/events'),
         api.community_events.GetActiveEventsApi.as_view()),

    path(_api_url('register'), api.register.Register.as_view()),
    path(_api_url('user'), api.user_data.SelfInfo.as_view()),
    path(_api_url('cookies/cookie_banner.js'),
         api.cookies.get_dynamic_cookie_banner_js),
    path(_api_url('user/confirm_match'), api.user.ConfirmMatchesApi.as_view()),
    path(_api_url('user/unmatch_self'), api.user.unmatch_self),
    path(_api_url('user/search_state/<str:state_slug>', end_slash=False),
         api.user.UpdateSearchingStateApi.as_view()),
    path(_api_url('user/login'), api.user.LoginApi.as_view()),

    *([path(_api_url('devlogin'), api.developers.DevLoginAPI.as_view())]  # Dev login only to be used in staging!
      if settings.IS_STAGE or settings.IS_DEV else []),

    path(_api_url('user/logout'), api.user.LogoutApi.as_view()),
    path(_api_url('user/checkpw'), api.user.CheckPasswordApi.as_view()),
    path(_api_url('user/changepw'), api.user.ChangePasswordApi.as_view()),
    path(_api_url('user/translate'), api.translation_requests.translate),
    path(_api_url('user/change_email'), api.user.ChangeEmailApi.as_view()),

    path(_api_url('emails/toggle_sub'), api.email_settings.unsubscribe_link),
    path(_api_url('emails/settings_update/'), api.email_settings.unsubscribe_email),

    path(_api_url('video_rooms/authenticate_call'),
         api.twilio.AuthenticateCallRoom.as_view()),

    path(_api_url('video_rooms/twillio_callback', end_slash=True),
         api.twilio.TwilioCallbackApi.as_view()),

    path(_api_url('profile'),
         api.profile.ProfileViewSet.as_view({"post": "partial_update", "get": "_get"})),
    path(_api_url('profile/completed'),
         api.profile.ProfileCompletedApi.as_view()),

    path(_api_url('notification'),
         api.notify.NotificationGetApi.as_view()),
    path(_api_url('notification/<str:action>', end_slash=False),
         api.notify.NotificationActionApi.as_view()),

    # e.g.: /user/verify/email/Base64{d=email&u=hash&k=pin:hash}
    path(_api_url('user/verify/email/<str:auth_data>', end_slash=False),
         api.user.VerifyEmail.as_view()),

    path(_api_url('user/verify/email_resend'),
         api.user.resend_verification_mail),

    # api that allows users to confirm or deny a pre-matching
    path(_api_url('user/match/confirm_deny'),
         api.confirm_match.confrim_match),
    # Admin
    path(_api_url('user/get', admin=True), api.admin.GetUser.as_view()),
    path(_api_url('user/list', admin=True), api.admin.UserList.as_view()),

    path(_api_url('graph/get', admin=True), fetch_graph),
    path(_api_url('user_list/get', admin=True), fetch_list),

    path(_api_url('user/tag/<str:action>', admin=True),
         api.admin.UserTaggingApi.as_view()),

    path(_api_url('user/update_score', admin=True),
         api.admin.RequestMatchingScoreUpdate.as_view()),

    path(_api_url('user/match', admin=True),
         api.admin.MakeMatch.as_view()),

    path(_api_url('user/unmatch', admin=True),
         api.admin.UnmatchUsers.as_view()),
    #    path(_api_url('user/match', admin=True), api.admin.MakeMatch.as_view()),
    #    path(_api_url('user/suggest_match', admin=True),
    #         api.admin.MatchingSuggestion.as_view()),
    path(_api_url('help_message'),
         api.help.SendHelpMessage.as_view()),
    *router.urls
]

view_routes = [
    path("", RedirectView.as_view(  # Redirect all requests to "/" to "/app/" per default
         url=f"app/", permanent=True), name="frontend_redirect"),

    path("register/", register, name="register"),
    path("password_reset/", forgot_password, name="password_reset"),
    path("set_password/<str:usr_hash>/<str:token>",
         set_password_reset, name="set_password_reset"),

    path("new_password_set/", password_set_success,
         name="password_reset_succsess"),

    path("password_reset_mail_send/", password_reset_mail_send,
         name="password_reset_succsess"),

    path("login/", login, name="login"),

    path("formpage/", subsection_of_user_form, name="formpage"),

    path('mailverify/', email_verification, name="email_verification"),
    path('mailverify_link/<str:auth_data>', email_verification_link_screen,
         name="email_verification_link"),
    path('change_email/', email_change, name="email_change"),
    path('mailverify/sucess/', email_verification_sucess,
         name="email_verification_sucess"),
    path('mailverify/fail/', email_verification_fail,
         name="email_verification_fail"),

    path('error/', error, name="error"),

    # The user form ( does its own routing )
    path(f"form/", user_form, name="user_form"),
    re_path(fr'^form/(?P<path>.*)$', user_form),

    path(f"form_v2/", user_form_v2, name="user_form_v2"),
    re_path(fr'^form_v2/(?P<path>.*)$', user_form_v2),

    # The main frontend ( does its own routing )
    path('app/', views.MainFrontendView.as_view(), name="main_frontend"),
    re_path(fr'^app/(?P<path>.*)$',
            views.MainFrontendView.as_view(), name="main_frontend_w_path"),

    path(f"admin_panel/", admin_panel, name="admin_panel"),
    path(f"admin_panel_v2/", admin_panel_v2, name="admin_panel_v2"),
    path(f"admin_panel_v2/<str:query_set>/", admin_panel_v2, name="admin_panel_v2"),
    
    path(_api_url('user_advanced/<str:pk>', admin=True), root_user_viewset),
    path(_api_url('user_listing_advanced/<str:list>', admin=True), advanced_user_listing),

    path(f"manage/", user_list_frontend, name="management_panel"),
    path(f"stats/graph/<str:slug>", graph_panel, name="graph_dashboard"),
    path(f"stats/<str:regrouped_by>", stats_panel, name="stats_dashboard"),

]

urlpatterns = [
    *view_routes,
    *api_routes,
]
