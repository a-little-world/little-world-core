from django.conf import settings
from django.urls import path, re_path
from django_rest_passwordreset.views import ResetPasswordConfirmViewSet, ResetPasswordValidateTokenViewSet
from rest_framework.routers import DefaultRouter

from management.api import (
    ai,
    app_integrity,
    calcom,
    community_events,
    confirm_match,
    cookies,
    developers,
    email_settings,
    firebase,
    googletrans,
    help,
    matches,
    notifications,
    notify,
    options,
    prematch_appointment_advanced,
    profile,
    push_notifications,
    register,
    report_unmatch,
    scores_advanced,
    slack,
    trans,
    translation_requests,
    user,
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
from management.api.native_auth import api_urls as api_urls_native_auth
from management.api.newsletter_subscribe import public_newsletter_subscribe
from management.api.questions import archive_card, get_question_cards
from management.api.scores import (
    burst_calculate_matching_scores_v2,
    delete_all_matching_scores,
    get_active_burst_calculation,
    list_top_scores,
    score_maximization_matching,
)
from management.api.short_links import api_urls as short_links_api_urls
from management.api.user_advanced import api_urls as user_advanced_api_urls
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

user_data_apis = [
    path("api/api_options", options.api_options),
    path("api/user", user.user_profile, name="user_profile_api"),
    path("api/notifications", notifications.notifications, name="notifications_api"),
    path("api/matches", matches.matches, name="matches_api"),
    path("api/community", community_events.community_events, name="community_events_api"),
    path("api/translations", trans.api_translations, name="api_translations_api"),
    path("api/firebase", firebase.firebase_config, name="firebase_config_api"),
]

api_routes = [
    *short_links_api_urls,
    *slack.api_routes,
    *ai.api_routes,
    *user_advanced_api_urls,
    *matches_advanced_api_urls,
    *scores_advanced.api_urls,
    *videocalls_advanced.api_urls,
    *user_advanced_statistics.api_urls,
    *prematch_appointment_advanced.api_urls,
    *user_data_apis,
    # User
    path("api/trans", trans.get_translation_catalogue),
    path("api/trans/<str:lang>/", trans.get_translation_catalogue),
    path("api/register/", register.Register.as_view()),
    path(
        "api/cookies/cookie_banner.js",
        cookies.get_dynamic_cookie_banner_js,
    ),
    path("api/user/confirm_match/", user.ConfirmMatchesApi.as_view()),
    path(
        "api/user/search_state/<str:state_slug>",
        user.UpdateSearchingStateApi.as_view(),
    ),
    path("api/user/login/", user.LoginApi.as_view()),
    *api_urls_native_auth,
    path("api/matching/report/", report_unmatch.report),
    path("api/matching/unmatch/", report_unmatch.unmatch),
    *(
        [path("api/devlogin/", developers.DevLoginAPI.as_view())]  # Dev login only to be used in staging!
        if (settings.IS_STAGE or settings.IS_DEV or settings.EXPOSE_DEV_LOGIN)
        else []
    ),
    path("api/user/logout/", user.LogoutApi.as_view()),
    path("api/user/checkpw/", user.CheckPasswordApi.as_view()),
    path("api/user/changepw/", user.ChangePasswordApi.as_view()),
    path("api/user/translate/", translation_requests.translate),
    path("api/googletrans/translate/", googletrans.translate),
    path("api/user/change_email/", user.ChangeEmailApi.as_view()),
    path("api/emails/toggle_sub/", email_settings.unsubscribe_link),
    path("api/emails/settings_update/", email_settings.unsubscribe_email),
    path(
        "api/profile/",
        profile.ProfileViewSet.as_view({"post": "partial_update", "get": "_get"}),
    ),
    path("api/profile/completed/", profile.ProfileCompletedApi.as_view()),
    path(
        "api/profile/<str:partner_hash>/match",
        matches.get_match,
    ),
    # e.g.: /user/verify/email/Base64{d=email&u=hash&k=pin:hash}
    path(
        "api/user/verify/email/<str:auth_data>",
        user.VerifyEmail.as_view(),
    ),
    path("api/user/verify/email_resend/", user.resend_verification_mail),
    path("api/user/match/confirm_deny/", confirm_match.confirm_match),
    path("api/matching/make_match", matches.make_match),
    path("api/help_message/", help.SendHelpMessage.as_view()),
    path("api/integrity/challenge", app_integrity.app_integrity_challenge),
    path("api/integrity/verify_android", app_integrity.app_integrity_verify_android),
    path("api/integrity/verify_ios", app_integrity.app_integrity_verify_ios),
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
        user.still_active_callback,
        name="still_active_callback",
    ),
    path("api/user/question_cards/", get_question_cards, name="question_cards"),
    path("api/user/archive_card/", archive_card, name="question_cards_archive"),
    path(
        "api/user/delete_account/",
        user.delete_account,
        name="delete_account_api",
    ),
    path(
        "api/newsletter_subscribe",
        public_newsletter_subscribe,
        name="newsletter_subscribe",
    ),
    path("api/admin/quick_matching_statistics/", get_quick_statistics),
    path("api/admin/optimize_possible_matches/", score_maximization_matching),
    path("api/matching/burst_update_scores/", burst_calculate_matching_scores_v2),
    path("api/matching/get_active_burst_calculation/", get_active_burst_calculation),
    path("api/admin/delete_all_matching_scores/", delete_all_matching_scores),
    path("api/admin/top_scores/", list_top_scores),
    path("info_card_debug/", main_frontend.debug_info_card, name="info_card"),
    path("api/calcom/", calcom.callcom_websocket_callback),
    *matching_panel.view_urls,
    *email_templates.view_urls,
    *admin_panel_emails.email_view_routes,
    *admin_panel_devkit.devkit_urls,
    path("api/dynamic_user_lists/", dynamic_user_list_general_api),
    path("api/dynamic_user_lists/<int:pk>/", dynamic_user_list_single_api),
    path("api/dynamic_user_lists/<int:list_id>/<int:user_id>/", dynamic_user_list_single_user_api),
    *notify.api_routes,
    *push_notifications.api_urls,
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
