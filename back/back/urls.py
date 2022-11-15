from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


"""
We are adding all app urls under `'/'` their paths should be set under `<app>/urls.py`
Admin paths registered last
"""

urlpatterns = [
    path('', include('management.urls')),
    path('', include('emails.urls')),
    path('admin/', admin.site.urls),
    path("cookies/", include("cookie_consent.urls")),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


if settings.BUILD_TYPE in ['staging', 'development']:
    # TODO: these views should also be blocked for admin only acess
    urlpatterns += [
        path('db/', include('django_spaghetti.urls')),
        # Don't expose the api shemas in production!
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/schema/swagger-ui/',
             SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/schema/redoc/',
             SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ]
