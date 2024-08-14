from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from management.models.state import State
from django.shortcuts import render
from typing import OrderedDict
from django.urls import path
from rest_framework.response import Response
from django.http import HttpResponse

@api_view(['GET'])
@permission_classes([])
def email_templates(request, menu=None):
    return render(request, "email_templates.html")

from dataclasses import dataclass

@dataclass
class BackendEmailTemplate:
    title: str
    template: str

view_urls = [
    path(f"email_templates/", email_templates, name="email_templates"),
]