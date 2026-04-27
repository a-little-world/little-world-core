from django.conf import settings
from django.urls import path, re_path
from django_rest_passwordreset.views import ResetPasswordConfirmViewSet, ResetPasswordValidateTokenViewSet
from rest_framework.routers import DefaultRouter

from management.api import (
    ai,
    app_integrity,
    banner,
    calcom,
    community_events,
    confirm_match,
    cookies,
    email_settings,
    firebase,
    help,
    matches,
    notifications,
    options,
    prematch_appointment_advanced,
    profile,
    push_notifications,
    register,
    report_unmatch,
    scores_advanced,
    slack,
    trans,
    translator,
    user_advanced_statistics,
    videocalls_advanced,
)
from management.api.dev_e2e_tests import api_urls as dev_e2e_test_api_urls
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
from management.api.scores import api_urls as scores_api_urls
from management.api.short_links import api_urls as short_links_api_urls
from management.api.still_in_contact import api_urls as still_in_contact_api_urls
from management.api.user import api_urls as user_api_urls
from management.api.user_advanced import api_urls as user_advanced_api_urls
from management.api.utils_advanced import CustomResetPasswordRequestTokenViewSet
from management.views import (
    admin_panel_devkit,
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
    path("api/matches", matches.matches, name="matches_api"),
    *user_api_urls,
    path("api/community", community_events.community_events, name="community_events_api"),
    path(
        "api/admin/community_events/",
        community_events.admin_community_events,
        name="admin_community_events_api",
    ),
    path(
        "api/admin/community_events/<int:pk>/",
        community_events.admin_community_event_detail,
        name="admin_community_event_detail_api",
    ),
    path(
        "api/admin/banners/",
        banner.admin_banners,
        name="admin_banners_api",
    ),
    path(
        "api/admin/banners/<int:pk>/",
        banner.admin_banner_detail,
        name="admin_banner_detail_api",
    ),
    path("api/translations", trans.api_translations, name="api_translations_api"),
    path("api/firebase", firebase.firebase_config, name="firebase_config_api"),
]

api_routes = [
    *short_links_api_urls,
    *slack.api_routes,
    *ai.api_routes,
    *user_advanced_api_urls,
    *matches_advanced_api_urls,
    *still_in_contact_api_urls,
    *scores_advanced.api_urls,
    *videocalls_advanced.api_urls,
    *user_advanced_statistics.api_urls,
    *prematch_appointment_advanced.api_urls,
    *user_data_apis,
    *notifications.api_urls,
    *push_notifications.api_urls,
    # User
    path("api/trans", trans.get_translation_catalogue),
    path("api/trans/<str:lang>/", trans.get_translation_catalogue),
    path("api/register/", register.Register.as_view()),
    path("api/register/android", register.RegisterAndroid.as_view()),
    path("api/register/ios", register.RegisterIOS.as_view()),
    path(
        "api/cookies/cookie_banner.js",
        cookies.get_dynamic_cookie_banner_js,
    ),
    path("api/translator/translate/", translator.translate),
    path("api/translator/languages/", translator.languages),
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
    *api_urls_native_auth,
    path("api/matching/report_match/", report_unmatch.report),
    path("api/matching/unmatch/", report_unmatch.unmatch),
    path("api/user/match/confirm_deny/", confirm_match.confirm_match),
    path("api/matching/make_match", matches.make_match),
    path("api/help_message/", help.SendHelpMessage.as_view()),
    path("api/integrity/challenge", app_integrity.app_integrity_challenge),
    *(dev_e2e_test_api_urls if settings.E2E_TEST_APIS_ENABLED else []),
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
    path("api/user/question_cards/", get_question_cards, name="question_cards"),
    path("api/user/archive_card/", archive_card, name="question_cards_archive"),
    path(
        "api/newsletter_subscribe",
        public_newsletter_subscribe,
        name="newsletter_subscribe",
    ),
    path("api/admin/quick_matching_statistics/", get_quick_statistics),
    *scores_api_urls,
    path("info_card_debug/", main_frontend.debug_info_card, name="info_card"),
    path("api/calcom/", calcom.callcom_websocket_callback),
    *matching_panel.view_urls,
    *email_templates.view_urls,
    *admin_panel_devkit.devkit_urls,
    path("api/dynamic_user_lists/", dynamic_user_list_general_api),
    path("api/dynamic_user_lists/<int:pk>/", dynamic_user_list_single_api),
    path("api/dynamic_user_lists/<int:list_id>/<int:user_id>/", dynamic_user_list_single_user_api),
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
