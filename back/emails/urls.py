from django.urls import path
from rest_framework import routers

from emails import depricated_api
from emails.api import backend_templates, dev_update_backend_emails, dynamic_template, email_settings, send_email

router = routers.SimpleRouter()
router.register("api/admin/email/logs", depricated_api.EmailListView)


api_routes = [
    path("api/admin/email/templates/", depricated_api.ListEmailTemplates.as_view()),
    path("api/admin/email/templates/encode/", depricated_api.EncodeTemplate.as_view()),
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
