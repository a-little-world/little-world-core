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
from rest_framework import serializers

def get_unsubscribed_categories():
    unsubscribale_categories = [category for category in EMAILS_CONFIG.categories if EMAILS_CONFIG.categories[category].unsubscribe]
    return unsubscribale_categories

@api_view(["GET"])
@permission_classes([])
@authentication_classes([])
def retrieve_email_settings(request, email_settings_hash):

    settings = EmailSettings.objects.filter(hash=email_settings_hash) 
    if not settings.exists():
        return Response({"detail": "Not found"}, status=404)
    
    settings = settings.first()
    
    unsubscribale_categories = get_unsubscribed_categories()
    subscribed_categories = [category for category in unsubscribale_categories if (category not in settings.unsubscribed_categories)]
    
    return Response({
        "categories": unsubscribale_categories,
        "unsubscribed_categories": settings.unsubscribed_categories,
        "subscribed_categories": subscribed_categories
    })
    
def toggle_category_subscribe(request, email_settings_hash, category, subscribed=False):
    settings = EmailSettings.objects.filter(hash=email_settings_hash) 
    if not settings.exists():
        return Response({"detail": "Not found"}, status=404)
    
    settings = settings.first()
    
    unsubscribale_categories = get_unsubscribed_categories()
    if category not in unsubscribale_categories:
        return Response({"detail": "Invalid category"}, status=400)
    
    if not subscribed:
        # Unsubscribe
        if category in settings.unsubscribed_categories:
            return Response({"detail": "Already unsubscribed"}, status=400)
        else:
            settings.unsubscribed_categories.append(category)
            return Response({"detail": f"Ubscubscribed '{category}'"})
    else:
        # Subscribe
        if category not in settings.unsubscribed_categories:
            return Response({"detail": "Already subscribed"}, status=400)
        else:
            settings.unsubscribed_categories.remove(category)
            return Response({"detail": f"Subscribed '{category}'"})
        
@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
def unscubscribe_category(request, email_settings_hash, category):
    return toggle_category_subscribe(request, email_settings_hash, category, subscribed=False)

@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
def subscribe_category(request, email_settings_hash, category):
    return toggle_category_subscribe(request, email_settings_hash, category, subscribed=True)
    
api_urls = [
    path("api/email_settings/<str:email_settings_hash>/", retrieve_email_settings),
    path("api/email_settings/<str:email_settings_hash>/<str:category>/subscribe", unscubscribe_category),
    path("api/email_settings/<str:email_settings_hash>/<str:category>/unsubscribe", subscribe_category),
]