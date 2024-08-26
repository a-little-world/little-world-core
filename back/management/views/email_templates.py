from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import render
from django.urls import path


@api_view(["GET"])
@permission_classes([])
def email_templates(request, menu=None):
    return render(request, "email_templates.html")


from dataclasses import dataclass


@dataclass
class BackendEmailTemplate:
    title: str
    template: str


view_urls = [
    path("email_templates/", email_templates, name="email_templates"),
]
