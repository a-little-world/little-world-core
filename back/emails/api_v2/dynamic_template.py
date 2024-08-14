import json
import os
import importlib
from management.helpers import IsAdminOrMatchingUser
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
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter, extend_schema_view
from django.template import Template, Context
from emails.models import DynamicTemplateSerializer, DynamicTemplate
from rest_framework import viewsets, filters
from management.views.matching_panel import DetailedPaginationMixin

@extend_schema_view(
    list=extend_schema(summary='List users'),
    retrieve=extend_schema(summary='Retrieve user'),
)
class DynamicEmailTemplateViewset(viewsets.ModelViewSet):
    queryset = DynamicTemplate.objects.all()

    serializer_class = DynamicTemplateSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    
    def retrieve(self, request, *args, **kwargs):
        template_name = kwargs['template_name']
        template = DynamicTemplate.objects.get(template_name=template_name)
        template_data = DynamicTemplateSerializer(template).data
        return Response(template_data)


api_urls = [
    path('api/matching/emails/dynamic_templates/', DynamicEmailTemplateViewset.as_view({ 'get': 'list', 'post': 'create' })),
    path('api/matching/emails/dynamic_templates/<str:template_name>/', DynamicEmailTemplateViewset.as_view({ 'get': 'retrieve' })),
]