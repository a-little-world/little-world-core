from django.urls import path, re_path
from .views import ViewEmail
from back.utils import _api_url
from . import api

api_routes = [
    path(_api_url('email/templates', admin=True),
         api.ListEmailTemplates.as_view())
]

urlpatterns = [
    *api_routes,
    path('emails/<str:mail_name>', ViewEmail.as_view(), name='view_mail'),
]
