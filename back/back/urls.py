from dataclasses import dataclass
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.response import Response
from rest_framework import status
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.urls import path, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LoginView
from management.urls import public_routes_wildcard

"""
We are adding all app urls under `'/'` their paths should be set under `<app>/urls.py`
Admin paths registered last
"""


handler404 = "management.views.main_frontend.handler404"
handler500 = "management.views.main_frontend.handler500"

statics = [
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    *static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
]

urlpatterns = [
    path('', include(('management.urls', 'management'), namespace="management")),
    path('', include('emails.urls')),
    path('', include('tracking.urls')),
    path('admin/', admin.site.urls),
    path("cookies/", include("cookie_consent.urls")),
    path('hijack/', include('hijack.urls')),
    path("", include("chat.django_private_chat2.urls")),

    # In staging and production we are serving statics from an aws bucket!
    *(statics if settings.IS_DEV else [])
]


# These view have extra accesibility control via 'management.middleware'
urlpatterns += [
    path('martor/', include('martor.urls')),

    path('db/', include('django_spaghetti.urls')),
    # Don't expose the api shemas in production!
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/',
         SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/',
         SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DOCS_PROXY:
    from revproxy.views import ProxyView

    view = ProxyView.as_view(
        upstream=settings.DJ_DOCS_URL)

    def auth_docs(request, **kwargs):
        from management.models.state import State
        if request.user.is_authenticated and \
                request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.DOCS_VIEW):
            return view(request, **kwargs)
        return HttpResponse("Not authenticated or insufficient permissions to view docs", status=status.HTTP_403_FORBIDDEN)

    urlpatterns += [
        re_path(fr'^docs/(?P<path>.*)$', auth_docs),
    ]

if settings.DOCS_BUILD:
    # If DOCS_BUILD we only use this route!
    urlpatterns = statics

if settings.USE_SENTRY:
    from django.views.decorators.csrf import csrf_exempt

    def trigger_error(request):
        division_by_zero = 1 / 0

    urlpatterns += [
        path('sentry-debug/', trigger_error),
    ]
    

urlpatterns += [public_routes_wildcard]