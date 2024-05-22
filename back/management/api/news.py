import datetime
from rest_framework.views import APIView
from rest_framework import authentication, permissions, viewsets
from rest_framework.response import Response
from management.models.news_and_updates import NewsItem, NewsItemSerializer


def get_all_active_news_items_serialized():
    active_event = list(NewsItem.get_all_active_news_items())
    return [NewsItemSerializer(e).data for e in active_event]


class GetActiveNewsItemsApi(APIView):
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(get_all_active_news_items_serialized())
