from django.conf import settings
from emails.mails import templates
from management.views.admin_panel_v2 import IsAdminOrMatchingUser
from rest_framework import serializers, status
from django.template.loader import render_to_string
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.core.paginator import Paginator
from back.utils import dataclass_as_dict
from back.utils import _api_url
from django.urls import path, re_path
from dataclasses import dataclass, asdict, fields, MISSING

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def is_devkit_enabled(request):
    return Response({"enabled": settings.IS_DEV})

devkit_urls = [
    path(_api_url('devkit/enabled', admin=True), is_devkit_enabled),
] if settings.IS_DEV else []