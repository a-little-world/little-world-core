from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from management.models.state import State
from django.shortcuts import render
from typing import OrderedDict
from django.urls import path
from rest_framework.response import Response
from django.http import HttpResponse

class IsAdminOrMatchingUser(BasePermission):
    """
    Allows access only to admin users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff) or \
            bool(request.user and request.user.is_authenticated and request.user.state.has_extra_user_permission(
                State.ExtraUserPermissionChoices.MATCHING_USER))

@api_view(['GET'])
@permission_classes([])
def email_templates(request, menu=None):
    return render(request, "email_templates.html")

view_urls = [
    path(f"email_templates/", email_templates, name="email_templates"),
]