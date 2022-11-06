from . import views, api
from django.urls import path
from django.conf import settings
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

VERSION = 1

urlpatterns = [
    path(f"api/v{VERSION}/user_data/", api.user_data.UserData.as_view()),
    path(f"api/v{VERSION}/register/", api.register.Register.as_view()),
    path(f"app/", views.example_frontend),
    *([  # Don't expose the api shemas in production!
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/schema/swagger-ui/',
             SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/schema/redoc/',
             SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ] if settings.BUILD_TYPE in ['development', 'staging'] else [])
]
