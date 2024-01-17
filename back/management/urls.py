from management import api
from django.urls import path, re_path
from django.contrib import admin
from django.conf import settings
from management.views import main_frontend, landing_page
from back.utils import _api_url
from django.conf.urls import include
from django.views.generic.base import RedirectView
from rest_framework import routers
from management.views.admin_panel_frontend import admin_panel, stats_panel, graph_panel, fetch_graph, user_list_frontend, fetch_list
from management.views import admin_panel_v2
from management.views import admin_panel_v2_actions

from rest_framework.routers import DefaultRouter
from django_rest_passwordreset.views import ResetPasswordValidateTokenViewSet, ResetPasswordConfirmViewSet, \
    ResetPasswordRequestTokenViewSet
from .api.questions import *

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

from rest_framework.decorators import api_view, authentication_classes, permission_classes
@permission_classes([])
@authentication_classes([])
@api_view(['POST'])
def challenge(request):
    print(request.data)
    if "challenge"  in request.data:
         return Response(request.data["challenge"])
    return Response()


from django.views.decorators.csrf import csrf_exempt


api_routes = [
    path("challenge", csrf_exempt(challenge)),
    # User
    path(_api_url('user_data'), api.user_data.UserData.as_view()),
    path(_api_url('user_data_v2'), api.user_data.user_data_v2),

    path(_api_url('trans/<str:lang>'), api.trans.TranslationsGet.as_view()),

    path(_api_url('options_translations'), api.options.get_translations_and_options),


    path(_api_url('community/events'),
         api.community_events.GetActiveEventsApi.as_view()),

    path(_api_url('register'), api.register.Register.as_view()),
    path(_api_url('user'), api.user_data.SelfInfo.as_view()),
    path(_api_url('cookies/cookie_banner.js', end_slash=False),
         api.cookies.get_dynamic_cookie_banner_js),
    path(_api_url('user/confirm_match'), api.user.ConfirmMatchesApi.as_view()),
    path(_api_url('user/unmatch_self'), api.user.unmatch_self),
    path(_api_url('user/search_state/<str:state_slug>', end_slash=False),
         api.user.UpdateSearchingStateApi.as_view()),
    path(_api_url('user/login'), api.user.LoginApi.as_view()),

    path(_api_url('matching/report'), api.report_unmatch.report),
    path(_api_url('matching/unmatch'), api.report_unmatch.unmatch),

    *([path(_api_url('devlogin'), api.developers.DevLoginAPI.as_view())]  # Dev login only to be used in staging!
      if (settings.IS_STAGE or settings.IS_DEV or settings.EXPOSE_DEV_LOGIN) else []),

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

    path(_api_url('question'),
         QuestionApi.as_view()),
    path(_api_url('questions/archive'),
         ArchivedQuestionsApi.as_view()),
    path(_api_url('questions-list/userarchived'),
         ViewArchivedList.as_view()),
    path(_api_url('questions/unarchived'),
         UnArchivedCard.as_view()),
    path(_api_url('matches/confirmed'),
         api.user_data.ConfirmedDataApi.as_view()),
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

    path("set_password/<str:usr_hash>/<str:token>",
         main_frontend.set_password_reset, name="set_password_reset"),

    path('mailverify_link/<str:auth_data>', main_frontend.email_verification_link,
         name="email_verification_link"),

    # The main frontend ( does its own routing )
    path('app/', main_frontend.MainFrontendView.as_view(), name="main_frontend"),
    re_path(fr'^app/(?P<path>.*)$',
            main_frontend.MainFrontendView.as_view(), name="main_frontend_w_path"),

    path(f"user/still_active/", api.user.still_active_callback, name="still_active_callback"),
    path(_api_url(f"user/delete_account", admin=False), api.user.delete_account, name="delete_account_api"),

    path(f"admin_panel/", admin_panel, name="admin_panel"),
    path(f"admin_panel_v2/", admin_panel_v2.admin_panel_v2, name="admin_panel_v2"),
    path(f"admin_panel_v2_login/", admin_panel_v2.admin_panel_v2_login, name="admin_panel_v2_login"),
    re_path(fr'^admin_panel_v2/(?P<menu>.*)$', admin_panel_v2.admin_panel_v2, name="admin_panel_v2"),
    path(_api_url('user_advanced/<str:pk>', admin=True), admin_panel_v2.root_user_viewset.as_view({'get': 'retrieve'})),
    path(_api_url('user_info/<str:pk>', admin=True), admin_panel_v2.user_info_viewset.as_view({'get': 'retrieve'})),
    path(_api_url('user_advanced/<str:pk>/notes', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'get': 'notes', 'post': 'notes'})),
    path(_api_url('user_advanced/<str:pk>/scores', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'get': 'scores'})),

    path(_api_url('user_advanced/<str:pk>/score_between', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'post': 'score_between'})),

    path(_api_url('user_advanced/<str:pk>/tasks', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'get': 'tasks', 'post': 'tasks'})),

    path(_api_url('user_advanced/<str:pk>/sms', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'get': 'sms'})),

    path(_api_url('user_advanced/<str:pk>/message_read', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'post': 'messages_mark_read'})),

    path(_api_url('user_advanced/<str:pk>/resend_email', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'post': 'resend_email'})),

    path(_api_url('user_advanced/<str:pk>/messages', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'get': 'messages'})),

    path(_api_url('user_advanced/<str:pk>/message_reply', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'post': 'messages_reply'})),

    path(_api_url('user_advanced/<str:pk>/tasks/complete', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'post': 'complete_task'})),

    path(_api_url('user_advanced/<str:pk>/request_score_update', admin=True),
         admin_panel_v2.root_user_viewset.as_view({'get': 'request_score_update'})),
    path(_api_url('user_listing_advanced/<str:list>', admin=True), admin_panel_v2.advanced_user_listing),
    path(_api_url('tasks/<str:task_id>/status', admin=True), admin_panel_v2.request_task_status),

    path(f"manage/", user_list_frontend, name="management_panel"),
    path(f"stats/graph/<str:slug>", graph_panel, name="graph_dashboard"),
    path(f"stats/<str:regrouped_by>", stats_panel, name="stats_dashboard"),
    
    path("info_card_debug/", main_frontend.info_card, name="info_card"),

    path(_api_url('calcom', admin=False), api.calcom.callcom_websocket_callback),
    
    
    *admin_panel_v2_actions.action_routes,


]

if settings.USE_LANDINGPAGE_PLACEHOLDER:
    view_routes += [
         path(f"landing/", landing_page.landing_page, name="landing_page_placeholder"),
    ]

urlpatterns = [
    *view_routes,
    *api_routes,
]

public_routes_wildcard = re_path(r'^(?P<path>.+?)/?$', main_frontend.PublicMainFrontendView.as_view(), name="main_frontend_public")
