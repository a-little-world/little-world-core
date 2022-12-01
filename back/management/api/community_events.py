import datetime
from rest_framework.views import APIView
from rest_framework import authentication, permissions, viewsets
from rest_framework.response import Response
from django.utils.translation import pgettext_lazy
from ..models.community_events import CommunityEvent, CommunityEventSerializer


def get_all_comunity_events_serialized():
    active_event = list(CommunityEvent.get_all_active_events())
    return [CommunityEventSerializer(e).data for e in active_event]


class GetActiveEventsApi(APIView):
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(get_all_comunity_events_serialized())
