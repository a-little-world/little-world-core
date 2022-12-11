from dataclasses import dataclass
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LoginView

"""
We are adding all app urls under `'/'` their paths should be set under `<app>/urls.py`
Admin paths registered last
"""

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
