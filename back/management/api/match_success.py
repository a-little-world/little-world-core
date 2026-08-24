from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from management.helpers import IsAdminOrMatchingUser
from management.match_success import documentation


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def match_success_documentation(request):
    """Live match-success docs: overview, active version, and every registered version."""
    return Response(documentation())


api_urls = [
    path("api/matching/match_success/", match_success_documentation),
]
