from django.conf import settings
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from management.helpers import IsAdminOrMatchingUser


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def is_devkit_enabled(request):
    return Response({"enabled": settings.IS_DEV})


devkit_urls = (
    [
        path("api/admin/devkit/enabled/", is_devkit_enabled),
    ]
    if settings.IS_DEV
    else []
)
