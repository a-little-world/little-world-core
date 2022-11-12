from . import views, api
from django.urls import path, re_path
from django.conf import settings
from . import views
from rest_framework import routers
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

VERSION = 1


def _api_url(slug, v=VERSION, admin=False):
    return f"api/admin/v{v}/{slug}/" if admin else f"api/v{v}/{slug}/"


router = routers.SimpleRouter()
# Register possible viewsets here ... TODO
api_routes = [
    path(_api_url('user_data'), api.user_data.UserData.as_view()),
    path(_api_url('register'), api.register.Register.as_view()),
    path(_api_url('self'), api.user_data.SelfInfo.as_view()),

    path(_api_url('user/get', admin=True), api.admin.GetUser.as_view()),
    path(_api_url('user/list', admin=True), api.admin.UserList.as_view()),
    #    path(_api_url('user/match', admin=True), api.admin.MakeMatch.as_view()),
    #    path(_api_url('user/suggest_match', admin=True),
    #         api.admin.MatchingSuggestion.as_view()),
    *router.urls
]

urlpatterns = [
    # Frontends:

    *api_routes,  # Add all API routes from above

    *([  # Don't expose the api shemas in production!
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/schema/swagger-ui/',
             SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/schema/redoc/',
             SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ] if settings.BUILD_TYPE in ['development', 'staging'] else []),

    re_path(fr'^app/(?P<path>.*)$', views.MainFrontendView.as_view()),
]
