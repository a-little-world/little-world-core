from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from management.urls import public_routes_wildcard
from management.views.cookie_banner_frontend import cookie_settings_page
from rest_framework import status

from back.build_types import BuildType

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

if settings.USE_AUTO_RELOAD:
    urlpatterns += [path("", include("django_simple_reload.api"))]

urlpatterns += [
    path("admin/", admin.site.urls),
    # The settings page is served by the cookie banner frontend. The exact `cookies/` /
    # `cookies` paths render it while `cookies/accept|decline/...` still resolve through
    # the cookie_consent include below.
    re_path(r"^cookies/?$", cookie_settings_page),
    path("cookies/", include("cookie_consent.urls")),
    path("hijack/", include("hijack.urls")),
    # In staging and production we are serving statics from an aws bucket!
    *(statics if settings.BUILD_TYPE == BuildType.DEVELOPMENT else []),
]

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
        if request.user.is_authenticated:
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

    def trigger_error(request: HttpRequest) -> HttpResponse:
        raise Exception("Sentry debug exception")
        return HttpResponse("Sentry debug endpoint")

    urlpatterns += [
        path("sentry-debug/", trigger_error),
    ]

urlpatterns += [public_routes_wildcard]
