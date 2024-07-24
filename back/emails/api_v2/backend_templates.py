import json
import os
import importlib
from management.views.matching_panel import IsAdminOrMatchingUser
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from management.models.state import State
from django.shortcuts import render
from django.urls import path
from rest_framework.response import Response
from django.http import HttpResponse
from django.template import Template, Context
from django.template.loader import get_template, render_to_string
from emails.api_v2.emails_config import EMAILS_CONFIG, EmailsConfig
from emails.api_v2.render_template import get_full_template_info, render_template_dynamic_lookup
from django.conf import settings
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter


@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def email_config(request):
    return Response(EMAILS_CONFIG.to_dict())


@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def show_template_info(request, template_name):
    template_config = EMAILS_CONFIG.emails.get(template_name)
    
    if not template_config:
        return Response({"error": "Template not found"}, status=404)
    
    return Response(get_full_template_info(template_config))

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def list_templates(request):

    templates = []
    for template_name in EMAILS_CONFIG.emails:

        template_config = EMAILS_CONFIG.emails.get(template_name)
        templates.append(get_full_template_info(template_config))
    return Response(templates)


@extend_schema(
    parameters=[
        OpenApiParameter(name="user_id", type=str, location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name="match_id", type=str, location=OpenApiParameter.QUERY, required=False),
    ]
)
@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def render_backend_template(request, template_name):
    template_config = EMAILS_CONFIG.emails.get(template_name)
    
    if not template_config:
        return Response({"error": "Template not found"}, status=404)
    
    template = template_config.template
    
    user_id = request.query_params.get("user_id", None)
    match_id = request.query_params.get("match_id", None)
    
    rendered = render_template_dynamic_lookup(template_name, user_id, match_id)
    return HttpResponse(rendered, content_type="text/html")

api_urls = [
    path('api/matching/emails/config/', email_config),
    path('api/matching/emails/templates/', list_templates),
    path('api/matching/emails/templates/<str:template_name>/', render_backend_template),
    path('api/matching/emails/templates/<str:template_name>/info/', show_template_info),
]