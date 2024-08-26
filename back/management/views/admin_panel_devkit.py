from django.conf import settings
from management.helpers import IsAdminOrMatchingUser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from back.utils import _api_url
from django.urls import path


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def is_devkit_enabled(request):
    return Response({"enabled": settings.IS_DEV})


devkit_urls = (
    [
        path(_api_url("devkit/enabled", admin=True), is_devkit_enabled),
    ]
    if settings.IS_DEV
    else []
)
