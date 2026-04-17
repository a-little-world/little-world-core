from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from management.authentication import NativeOnlyJWTAuthentication
from management.helpers.detailed_pagination import get_paginated_format_v2
from management.models.community_events import (
    AdminCommunityEventSerializer,
    CommunityEvent,
    CommunityEventSerializer,
)


def get_all_comunity_events_serialized():
    active_event = list(CommunityEvent.get_all_active_events())
    return [CommunityEventSerializer(e).data for e in active_event]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def community_events(request):
    """
    Returns community events data for the authenticated user (public view).
    """
    page = int(request.GET.get("page", 1))
    items_per_page = int(request.GET.get("page_size", 15))
    user = request.user

    try:
        events = get_paginated_format_v2(CommunityEvent.get_active_events_for_user(user), items_per_page, page)
        events["results"] = CommunityEventSerializer(events["results"], many=True).data

        return Response(events)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_community_events(request):
    """
    Admin view for listing and creating community events.
    Accessible to any authenticated user of the admin panel.
    """
    if request.method == "GET":
        events = CommunityEvent.objects.all().order_by("time")
        serializer = AdminCommunityEventSerializer(events, many=True)
        return Response(serializer.data)

    # POST – create new event
    serializer = AdminCommunityEventSerializer(data=request.data)
    if serializer.is_valid():
        event = serializer.save()
        return Response(AdminCommunityEventSerializer(event).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_community_event_detail(request, pk: int):
    """
    Admin view for updating an existing community event.
    """
    event = get_object_or_404(CommunityEvent, pk=pk)
    partial = request.method == "PATCH"
    serializer = AdminCommunityEventSerializer(event, data=request.data, partial=partial)
    if serializer.is_valid():
        event = serializer.save()
        return Response(AdminCommunityEventSerializer(event).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
