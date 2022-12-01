from rest_framework.views import APIView
from rest_framework import authentication, permissions, viewsets
from rest_framework.response import Response
from ..models.community_events import CommunityEvent, CommunityEventSerializer


class GetActiveEventsApi(APIView):
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        active_event = list(CommunityEvent.get_all_active_events())
        return Response([
            CommunityEventSerializer(e).data for e in active_event
        ])
