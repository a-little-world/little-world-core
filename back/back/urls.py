from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from management.urls import public_routes_wildcard
from rest_framework import status

"""
We are adding all app urls under `'/'` their paths should be set under `<app>/urls.py`
Admin paths registered last
"""


handler404 = "management.views.main_frontend.handler404"
handler500 = "management.views.main_frontend.handler500"

statics = [
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    *static(settings.STATIC_URL, document_root=settings.STATIC_ROOT),
]

urlpatterns = [
    path("", include("emails.urls")),
    path("", include(("management.urls", "management"), namespace="management")),
    path("", include("chat.urls")),
    path("", include("tracking.urls")),
    path("", include("video.urls")),
]

from tbs_django_auto_reload.api import urlpatters as auto_reload_urlpatters

if settings.USE_AUTO_RELOAD:
    urlpatterns += auto_reload_urlpatters

urlpatterns += [
    path("admin/", admin.site.urls),
    path("cookies/", include("cookie_consent.urls")),
    path("hijack/", include("hijack.urls")),
    # In staging and production we are serving statics from an aws bucket!
    *(statics if settings.IS_DEV else []),
]

if settings.DEBUG and settings.USE_DEBUG_TOOLBAR:
    try:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        print("Debug toolbar not installed")

# These view have extra accesibility control via 'management.middleware'
urlpatterns += [
    path("martor/", include("martor.urls")),
    path("db/", include("django_spaghetti.urls")),
    # Don't expose the api shemas in production!
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/patenmatch/", include("patenmatch.urls")),
]

if settings.DOCS_PROXY:
    from revproxy.views import ProxyView

    view = ProxyView.as_view(upstream=settings.DOCS_URL)

    def auth_docs(request, **kwargs):
        from management.models.state import State

        if request.user.is_authenticated and request.user.state.has_extra_user_permission(
            State.ExtraUserPermissionChoices.DOCS_VIEW
        ):
            return view(request, **kwargs)
        return HttpResponse(
            "Not authenticated or insufficient permissions to view docs", status=status.HTTP_403_FORBIDDEN
        )

    urlpatterns += [
        re_path(r"^docs/(?P<path>.*)$", auth_docs),
    ]

if settings.DOCS_BUILD:
    # If DOCS_BUILD we only use this route!
    urlpatterns = statics

if settings.USE_SENTRY:

    def trigger_error(request):
        division_by_zero = 1 / 0

    urlpatterns += [
        path("sentry-debug/", trigger_error),
    ]


urlpatterns += [public_routes_wildcard]
