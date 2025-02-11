from django.urls import path
from rest_framework import routers

from back.utils import _api_url
from emails import depricated_api
from emails.api import backend_templates, dev_update_backend_emails, dynamic_template, email_settings, send_email

router = routers.SimpleRouter()
router.register(_api_url("email/logs", admin=True, end_slash=False), depricated_api.EmailListView)


api_routes = [
    path(_api_url("email/templates", admin=True), depricated_api.ListEmailTemplates.as_view()),
    path(_api_url("email/templates/encode", admin=True), depricated_api.EncodeTemplate.as_view()),
    *router.urls,
]

urlpatterns = [
    *api_routes,
    *backend_templates.api_urls,
    *dev_update_backend_emails.api_urls,
    *send_email.api_urls,
    *dynamic_template.api_urls,
    *email_settings.api_urls,
]
