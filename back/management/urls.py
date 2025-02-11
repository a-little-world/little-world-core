from django.conf import settings
from django.urls import path, re_path
from django_rest_passwordreset.views import ResetPasswordConfirmViewSet, ResetPasswordValidateTokenViewSet
from rest_framework.routers import DefaultRouter

from back.utils import _api_url
from management import api
from management.api import (
    ai,
    notify,
    prematch_appointment_advanced,
    scores_advanced,
    slack,
    user_advanced_statistics,
    videocalls_advanced,
)
from management.api.dynamic_user_list import (
    DynamicUserListGeneralViewSet,
    DynamicUserListSingleUserViewSet,
    DynamicUserListSingleViewSet,
)
from management.api.matches_advanced import api_urls as matches_advanced_api_urls
from management.api.matching_stats import get_quick_statistics
from management.api.newsletter_subscribe import public_newsletter_subscribe
from management.api.questions import archive_card, get_question_cards
from management.api.scores import (
    burst_calculate_matching_scores_v2,
    delete_all_matching_scores,
    get_active_burst_calculation,
    list_top_scores,
    score_maximization_matching,
)
from management.api.user_advanced import api_urls as user_advanced_api_urls
from management.api.user_data import user_data_api
from management.api.utils_advanced import CustomResetPasswordRequestTokenViewSet
from management.views import (
    admin_panel_devkit,
    admin_panel_emails,
    email_templates,
    landing_page,
    main_frontend,
    matching_panel,
)

router = DefaultRouter()
router.register(  # TODO: we might even wan't to exclude this api
    r"api/user/resetpw/validate",
    ResetPasswordValidateTokenViewSet,
    basename="reset-password-validate",
)
router.register(
    r"api/user/resetpw/confirm",
    ResetPasswordConfirmViewSet,
    basename="reset-password-confirm",
)
router.register(
    r"api/user/resetpw",
    CustomResetPasswordRequestTokenViewSet,
    basename="reset-password-request",
)

dynamic_user_list_general_api = DynamicUserListGeneralViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
dynamic_user_list_single_api = DynamicUserListSingleViewSet.as_view(
    {
        "get": "list",
        "put": "update",
        "delete": "destroy",
    }
)
dynamic_user_list_single_user_api = DynamicUserListSingleUserViewSet.as_view(
    {
        "delete": "destroy",
    }
)

api_routes = [
    *slack.api_routes,
    *ai.api_routes,
    *user_advanced_api_urls,
    *matches_advanced_api_urls,
    *scores_advanced.api_urls,
    *videocalls_advanced.api_urls,
    *user_advanced_statistics.api_urls,
    *prematch_appointment_advanced.api_urls,
    # User
    path(_api_url("user_data_v2"), api.user_data.user_data_v2),
    path(_api_url("trans"), api.trans.get_translation_catalogue),
    path(_api_url("trans/<str:lang>"), api.trans.get_translation_catalogue),
    path(_api_url("options"), api.options.get_options),
    path(_api_url("community/events"), api.community_events.GetActiveEventsApi.as_view()),
    path(_api_url("register"), api.register.Register.as_view()),
    path(_api_url("user"), user_data_api, name="user_data_api"),
    path(
        _api_url("cookies/cookie_banner.js", end_slash=False),
        api.cookies.get_dynamic_cookie_banner_js,
    ),
    path(_api_url("user/confirm_match"), api.user.ConfirmMatchesApi.as_view()),
    path(
        _api_url("user/search_state/<str:state_slug>", end_slash=False),
        api.user.UpdateSearchingStateApi.as_view(),
    ),
    path(_api_url("user/login"), api.user.LoginApi.as_view()),
    path(_api_url("matching/report"), api.report_unmatch.report),
    path(_api_url("matching/unmatch"), api.report_unmatch.unmatch),
    *(
        [path(_api_url("devlogin"), api.developers.DevLoginAPI.as_view())]  # Dev login only to be used in staging!
        if (settings.IS_STAGE or settings.IS_DEV or settings.EXPOSE_DEV_LOGIN)
        else []
    ),
    path(_api_url("user/logout"), api.user.LogoutApi.as_view()),
    path(_api_url("user/checkpw"), api.user.CheckPasswordApi.as_view()),
    path(_api_url("user/changepw"), api.user.ChangePasswordApi.as_view()),
    path(_api_url("user/translate"), api.translation_requests.translate),
    path(_api_url("googletrans/translate"), api.googletrans.translate),
    path(_api_url("user/change_email"), api.user.ChangeEmailApi.as_view()),
    path(_api_url("emails/toggle_sub"), api.email_settings.unsubscribe_link),
    path(_api_url("emails/settings_update/"), api.email_settings.unsubscribe_email),
    path(
        _api_url("profile"),
        api.profile.ProfileViewSet.as_view({"post": "partial_update", "get": "_get"}),
    ),
    path(_api_url("profile/completed"), api.profile.ProfileCompletedApi.as_view()),
    path(
        _api_url("profile/<str:partner_hash>/match", end_slash=False),
        api.matches.get_match,
    ),
    path(_api_url("matches/confirmed"), api.user_data.ConfirmedDataApi.as_view()),
    # e.g.: /user/verify/email/Base64{d=email&u=hash&k=pin:hash}
    path(
        _api_url("user/verify/email/<str:auth_data>", end_slash=False),
        api.user.VerifyEmail.as_view(),
    ),
    path(_api_url("user/verify/email_resend"), api.user.resend_verification_mail),
    path(_api_url("user/match/confirm_deny"), api.confirm_match.confirm_match),
    path("api/matching/make_match", api.matches.make_match),
    path(_api_url("help_message"), api.help.SendHelpMessage.as_view()),
    *router.urls,
]

view_routes = [
    path("", main_frontend.MainFrontendRouter.as_view(), name="base_route"),
    path(
        "set_password/<str:usr_hash>/<str:token>",
        main_frontend.set_password_reset,
        name="set_password_reset",
    ),
    path(
        "mailverify_link/<str:auth_data>",
        main_frontend.email_verification_link,
        name="email_verification_link",
    ),
    path(
        "user/still_active/",
        api.user.still_active_callback,
        name="still_active_callback",
    ),
    path("api/user/question_cards/", get_question_cards, name="question_cards"),
    path("api/user/archive_card/", archive_card, name="question_cards_archive"),
    path(
        _api_url("user/delete_account", admin=False),
        api.user.delete_account,
        name="delete_account_api",
    ),
    path(
        "api/newsletter_subscribe",
        public_newsletter_subscribe,
        name="newsletter_subscribe",
    ),
    path(_api_url("quick_matching_statistics", admin=True), get_quick_statistics),
    path(_api_url("optimize_possible_matches", admin=True), score_maximization_matching),
    path("api/matching/burst_update_scores/", burst_calculate_matching_scores_v2),
    path("api/matching/get_active_burst_calculation/", get_active_burst_calculation),
    path(
        _api_url("delete_all_matching_scores", admin=True), delete_all_matching_scores
    ),  # TODO: can be depricated / is perforemed automaticly on update
    path(_api_url("top_scores", admin=True), list_top_scores),
    path("info_card_debug/", main_frontend.debug_info_card, name="info_card"),
    path(_api_url("calcom", admin=False), api.calcom.callcom_websocket_callback),
    *matching_panel.view_urls,
    *email_templates.view_urls,
    *admin_panel_emails.email_view_routes,
    *admin_panel_devkit.devkit_urls,
    path("api/dynamic_user_lists/", dynamic_user_list_general_api),
    path("api/dynamic_user_lists/<int:pk>/", dynamic_user_list_single_api),
    path("api/dynamic_user_lists/<int:list_id>/<int:user_id>/", dynamic_user_list_single_user_api),
    *notify.api_routes,
]


if settings.USE_LANDINGPAGE_PLACEHOLDER:
    view_routes += [
        path("landing/", landing_page.landing_page, name="landing_page_placeholder"),
    ]

urlpatterns = [
    *view_routes,
    *api_routes,
]

public_routes_wildcard = re_path(
    r"^(?P<path>.+?)/?$",
    main_frontend.MainFrontendRouter.as_view(),
    name="main_frontend_public",
)
