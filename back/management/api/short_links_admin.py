from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.models.short_links import AdminShortLinkSerializer, ShortLink


@api_view(["GET", "POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_short_links(request):
    """
    List active (non-archived) short links with optional search, or create a new link.
    """
    if request.method == "GET":
        search = (request.GET.get("search") or "").strip()
        qs = (
            ShortLink.objects.filter(archived_at__isnull=True)
            .annotate(click_count=Count("shortlinkclick"))
            .order_by("-updated_at")
        )
        if search:
            qs = qs.filter(Q(tag__icontains=search) | Q(url__icontains=search))
        serializer = AdminShortLinkSerializer(qs, many=True)
        return Response(serializer.data)

    serializer = AdminShortLinkSerializer(data=request.data)
    if serializer.is_valid():
        link = serializer.save()
        link.refresh_from_db()
        qs = ShortLink.objects.filter(pk=link.pk).annotate(click_count=Count("shortlinkclick"))
        out = AdminShortLinkSerializer(qs.first())
        return Response(out.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PATCH"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_short_link_detail(request, pk: int):
    """Update an existing short link (tag cannot be changed)."""
    short_link = get_object_or_404(ShortLink, pk=pk, archived_at__isnull=True)
    serializer = AdminShortLinkSerializer(short_link, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        short_link.refresh_from_db()
        qs = ShortLink.objects.filter(pk=short_link.pk).annotate(click_count=Count("shortlinkclick"))
        return Response(AdminShortLinkSerializer(qs.first()).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_short_link_archive(request, pk: int):
    """Archive a short link so it no longer redirects."""
    short_link = get_object_or_404(ShortLink, pk=pk, archived_at__isnull=True)
    short_link.archived_at = timezone.now()
    short_link.save(update_fields=["archived_at", "updated_at"])
    qs = ShortLink.objects.filter(pk=short_link.pk).annotate(click_count=Count("shortlinkclick"))
    return Response(AdminShortLinkSerializer(qs.first()).data)
