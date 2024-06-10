from management import api
from django.urls import path, re_path
from django.conf import settings
from management.views import main_frontend, landing_page
from back.utils import _api_url
from management.views.admin_panel_frontend import stats_panel, graph_panel, fetch_graph, user_list_frontend, fetch_list
from management.views import admin_panel_devkit
from management.views import admin_panel_emails
from management.views import matching_panel
from management.api import slack, ai
from management.api.scores import list_top_scores, score_maximization_matching, burst_calulate_matching_scores, delete_all_matching_scores
from management.api.matching_stats import get_quick_statistics
from management.api.questions import get_question_cards, archive_card
from management.api.newsletter_subscribe import public_newsletter_subscribe
from management.api.user_data import user_data_api
from management.api.user_advanced import api_urls as user_advanced_api_urls
from management.api.matches_advanced import api_urls as matches_advanced_api_urls

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



api_routes = [
    *slack.api_routes,
    *ai.api_routes,
    *user_advanced_api_urls,
    *matches_advanced_api_urls,
    # User
    path(_api_url('user_data_v2'), api.user_data.user_data_v2),

    path(_api_url('trans'), api.trans.get_translation_catalogue),
    path(_api_url('trans/<str:lang>'), api.trans.get_translation_catalogue),

    path(_api_url('options'), api.options.get_options),


    path(_api_url('community/events'),
         api.community_events.GetActiveEventsApi.as_view()),

    path(_api_url('register'), api.register.Register.as_view()),
    path(_api_url('user'), user_data_api, name="user_data_api"),
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
    path(_api_url('googletrans/translate'), api.googletrans.translate),
    path(_api_url('user/change_email'), api.user.ChangeEmailApi.as_view()),

    path(_api_url('emails/toggle_sub'), api.email_settings.unsubscribe_link),
    path(_api_url('emails/settings_update/'), api.email_settings.unsubscribe_email),

    path(_api_url('profile'),
         api.profile.ProfileViewSet.as_view({"post": "partial_update", "get": "_get"})),
    path(_api_url('profile/completed'),
         api.profile.ProfileCompletedApi.as_view()),
    path(_api_url('profile/<str:partner_hash>/match', end_slash=False),
         api.matches.get_match),

    path(_api_url('notification'),
         api.notify.NotificationGetApi.as_view()),
    path(_api_url('notification/<str:action>', end_slash=False),
         api.notify.NotificationActionApi.as_view()),

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
    path(_api_url('graph/get', admin=True), fetch_graph),
    path(_api_url('user_list/get', admin=True), fetch_list),

    path(_api_url('user/match', admin=True),
         api.matches.make_match),
    #    path(_api_url('user/match', admin=True), api.admin.MakeMatch.as_view()),
    #    path(_api_url('user/suggest_match', admin=True),
    #         api.admin.MatchingSuggestion.as_view()),
    path(_api_url('help_message'),
         api.help.SendHelpMessage.as_view()),
    *router.urls
]

view_routes = [
          
    path('', main_frontend.MainFrontendRouter.as_view(), name="base_route"),

    path("set_password/<str:usr_hash>/<str:token>",
         main_frontend.set_password_reset, name="set_password_reset"),

    path('mailverify_link/<str:auth_data>', main_frontend.email_verification_link,
         name="email_verification_link"),

    path(f"user/still_active/", api.user.still_active_callback, name="still_active_callback"),
    path(f"api/user/question_cards/",get_question_cards, name="question_cards"),
    path(f"api/user/archive_card/",archive_card, name="question_cards_archive"),

    path(_api_url(f"user/delete_account", admin=False), api.user.delete_account, name="delete_account_api"),

    
    path("api/newsletter_subscribe", public_newsletter_subscribe, name="newsletter_subscribe"),
    path(_api_url('quick_matching_statistics', admin=True), get_quick_statistics),
    path(_api_url('optimize_possible_matches', admin=True), score_maximization_matching),
    path(_api_url('burst_calulate_matching_scores', admin=True), burst_calulate_matching_scores),
    path(_api_url('delete_all_matching_scores', admin=True), delete_all_matching_scores),
    path(_api_url('top_scores', admin=True), list_top_scores),

    path(f"manage/", user_list_frontend, name="management_panel"),
    path(f"stats/graph/<str:slug>", graph_panel, name="graph_dashboard"),
    path(f"stats/<str:regrouped_by>", stats_panel, name="stats_dashboard"),
    
    path("info_card_debug/", main_frontend.info_card, name="info_card"),

    path(_api_url('calcom', admin=False), api.calcom.callcom_websocket_callback),
    
    *matching_panel.view_urls,
    
    *admin_panel_emails.email_view_routes,
    *admin_panel_devkit.devkit_urls,
]


if settings.USE_LANDINGPAGE_PLACEHOLDER:
    view_routes += [
         path(f"landing/", landing_page.landing_page, name="landing_page_placeholder"),
    ]

urlpatterns = [
    *view_routes,
    *api_routes,
]

public_routes_wildcard = re_path(r'^(?P<path>.+?)/?$', main_frontend.MainFrontendRouter.as_view(), name="main_frontend_public")
