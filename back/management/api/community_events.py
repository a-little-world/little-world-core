from rest_framework import authentication, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from management.models.community_events import CommunityEvent, CommunityEventSerializer
from management.helpers.detailed_pagination import get_paginated_format_v2


def get_all_comunity_events_serialized():
    active_event = list(CommunityEvent.get_all_active_events())
    return [CommunityEventSerializer(e).data for e in active_event]


class GetActiveEventsApi(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(get_all_comunity_events_serialized())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, JWTAuthentication])
def community_events(request):
    """
    Returns community events data for the authenticated user.
    """
    page = int(request.GET.get("page", 1))
    items_per_page = int(request.GET.get("page_size", 10))
    user = request.user
    
    try:
        events = get_paginated_format_v2(CommunityEvent.get_active_events_for_user(user), items_per_page, page)
        events["results"] = CommunityEventSerializer(events["results"], many=True).data
        
        return Response(events)
    except Exception as e:
        return Response({"error": str(e)}, status=400)
