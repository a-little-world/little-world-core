from django.urls import path
from rest_framework import routers

from emails.api import backend_templates, dev_update_backend_emails, dynamic_template, email_settings, send_email

urlpatterns = [
    *backend_templates.api_urls,
    *dev_update_backend_emails.api_urls,
    *send_email.api_urls,
    *dynamic_template.api_urls,
    *email_settings.api_urls,
]
