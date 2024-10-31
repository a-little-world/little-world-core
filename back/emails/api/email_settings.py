from management.helpers import IsAdminOrMatchingUser, DetailedPaginationMixin
from django.urls import path
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view
from emails.models import DynamicTemplateSerializer, DynamicTemplate
from rest_framework import viewsets
from emails.api.render_template import prepare_dynamic_template_context
from rest_framework.decorators import action
from management.api.user_advanced_filter_lists import get_list_by_name
from management.models.user import User
from emails.api.render_template import render_template_to_html
from django.template import Template, Context
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from django.core.mail import EmailMessage
from management.controller import get_base_management_user
from emails.models import EmailLog
from management.models.settings import EmailSettings
from emails.api.emails_config import EMAILS_CONFIG

@api_view(["GET"])
@permission_classes([])
@authentication_classes([])
def retrieve_email_settings(request, email_settings_hash):

    settings = EmailSettings.objects.filter(hash=email_settings_hash) 
    if not settings.exists():
        return Response({"detail": "Not found"}, status=404)
    
    settings = settings.first()
    
    unsubscribale_categories = [category.id for category in EMAILS_CONFIG.categories if category.unsubscribe]
    
    return Response({
        "categories": unsubscribale_categories,
        "unsubscribed_categories": settings.unsubscribed_categories
    })
    

api_urls = [
    path("email_settings/<str:email_settings_hash>/", retrieve_email_settings),
]