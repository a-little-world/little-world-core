from django.urls import path, re_path
from rest_framework import routers
from .views import ViewEmail
from back.utils import _api_url
from . import api

router = routers.SimpleRouter()
router.register(_api_url("email/logs", admin=True,
                end_slash=False), api.EmailListView)


api_routes = [
    path(_api_url('email/templates', admin=True),
         api.ListEmailTemplates.as_view()),
    *router.urls
]

urlpatterns = [
    *api_routes,
    path('emails/<str:mail_name>', ViewEmail.as_view(), name='view_mail'),
]
