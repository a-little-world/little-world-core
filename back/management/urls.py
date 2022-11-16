from . import views, api
from django.urls import path, re_path
from django.conf import settings
from . import views
from back.utils import _api_url
from rest_framework import routers


router = routers.SimpleRouter()
# Register possible viewsets here ... TODO
api_routes = [
    # User
    path(_api_url('user_data'), api.user_data.UserData.as_view()),

    path(_api_url('register'), api.register.Register.as_view()),
    path(_api_url('user'), api.user_data.SelfInfo.as_view()),
    path(_api_url('user/login'), api.user.LoginApi.as_view()),
    path(_api_url('profile'),
         api.profile.ProfileViewSet.as_view({"post": "partial_update", "get": "_get"})),

    path(_api_url('notification'),
         api.notify.NotificationGetApi.as_view()),
    path(_api_url('notification/<str:action>', end_slash=False),
         api.notify.NotificationActionApi.as_view()),


    # e.g.: /user/verify/email/Base64{d=email&u=hash&k=pin:hash}
    path(_api_url('user/verify/email/<str:auth_data>'),  # TODO create verify email api
         api.user.VerifyEmail.as_view()),

    # Admin
    path(_api_url('user/get', admin=True), api.admin.GetUser.as_view()),
    path(_api_url('user/list', admin=True), api.admin.UserList.as_view()),
    #    path(_api_url('user/match', admin=True), api.admin.MakeMatch.as_view()),
    #    path(_api_url('user/suggest_match', admin=True),
    #         api.admin.MatchingSuggestion.as_view()),
    *router.urls
]

urlpatterns = [

    *api_routes,  # Add all API routes from above


    # Frontends:
    re_path(fr'^app/(?P<path>.*)$', views.MainFrontendView.as_view()),
]
