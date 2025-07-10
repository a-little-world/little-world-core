from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from django.urls import path

from management.models.notifications import Notification, SelfNotificationSerializer
from management.helpers.detailed_pagination import get_paginated_format_v2


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def notifications(request):
    """
    Returns notification data for the authenticated user.
    """
    page = int(request.GET.get("page", 1))
    items_per_page = int(request.GET.get("page_size", 10))
    
    try:
        read_notifications = get_paginated_format_v2(Notification.get_read_notifications(request.user), items_per_page, page)
        read_notifications["results"] = SelfNotificationSerializer(read_notifications["results"], many=True).data

        unread_notifications = get_paginated_format_v2(Notification.get_unread_notifications(request.user), items_per_page, page)
        unread_notifications["results"] = SelfNotificationSerializer(unread_notifications["results"], many=True).data

        archived_notifications = get_paginated_format_v2(Notification.get_archived_notifications(request.user), items_per_page, page)
        archived_notifications["results"] = SelfNotificationSerializer(archived_notifications["results"], many=True).data
        
        return Response({
            "unread": unread_notifications,
            "read": read_notifications,
            "archived": archived_notifications,
        })
    except Exception as e:
        return Response({"error": str(e)}, status=400)
