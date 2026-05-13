from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse, urlunparse

from django.conf import settings
from django.db.models import Count, Q
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import get_paginated_format_v2
from management.models.short_links import AdminShortLinkSerializer, ShortLink, ShortLinkClick
from management.models.user import User


@api_view(["GET"])
def short_link_click(request, tag):
    short_link = get_object_or_404(ShortLink, tag=tag, archived_at__isnull=True)
    # Only associate the user if they're authenticated
    source = request.query_params.get("source", "none")
    user_hash = request.query_params.get("user_hash", "none")

    # also allow 'abreviations' for the query params
    if source == "none":
        source = request.query_params.get("s", "none")
    if user_hash == "none":
        user_hash = request.query_params.get("u", "none")
        if user_hash == "none":
            user_hash = request.query_params.get("h", "none")

    user = None
    if not request.user.is_authenticated:
        if user_hash:
            qs_user = User.objects.filter(hash=user_hash)
            if qs_user.exists():
                user = qs_user.first()
    else:
        user = request.user

    ShortLinkClick.objects.create(user=user, short_link=short_link, source=source)

    try:
        parsed_dest = urlparse(short_link.url)
        dest_qd = QueryDict(parsed_dest.query, mutable=True)
        for key in request.query_params:
            if key not in dest_qd:
                dest_qd.setlist(key, request.query_params.getlist(key))
        merged_url = urlunparse(parsed_dest._replace(query=dest_qd.urlencode()))
    except Exception:
        merged_url = short_link.url

    response = redirect(merged_url)

    if short_link.tracking_cookies_enabled:
        for cookie in short_link.tracking_cookies or []:
            response.set_cookie(
                cookie["name"],
                cookie["value"],
                max_age=60 * 60 * 24 * 30,  # 30 days
                domain=getattr(settings, "SESSION_COOKIE_DOMAIN", None),
                path="/",
                secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
                httponly=False,
                samesite=getattr(settings, "SESSION_COOKIE_SAMESITE", "Lax"),
            )
    return response


class AdminShortLinkClickSerializer(serializers.ModelSerializer):
    tag = serializers.CharField(source="short_link.tag", read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = ShortLinkClick
        fields = ["id", "tag", "user", "created_at", "source"]

    def get_user(self, obj):
        return obj.user.email if obj.user else "Anonymous"


def _parse_optional_date(raw_value: str | None, field_name: str) -> date | None:
    if not raw_value:
        return None
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise serializers.ValidationError({field_name: "Use YYYY-MM-DD."}) from exc


def _to_start_of_day(value: date) -> datetime:
    return timezone.make_aware(datetime.combine(value, time.min))


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


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_short_link_clicks(request):
    search = (request.GET.get("search") or "").strip()
    source = (request.GET.get("source") or "").strip()
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 50))

    try:
        start_date = _parse_optional_date(request.GET.get("start_date"), "start_date")
        end_date = _parse_optional_date(request.GET.get("end_date"), "end_date")
    except serializers.ValidationError as exc:
        return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

    if start_date and end_date and start_date > end_date:
        return Response(
            {"end_date": "End date must be on or after start date."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = ShortLinkClick.objects.select_related("short_link", "user").order_by("-created_at")

    if search:
        qs = qs.filter(short_link__tag__icontains=search)

    if source and source != "all":
        qs = qs.filter(source=source)

    if start_date:
        qs = qs.filter(created_at__gte=_to_start_of_day(start_date))

    if end_date:
        end_date_exclusive = _to_start_of_day(end_date + timedelta(days=1))
        qs = qs.filter(created_at__lt=end_date_exclusive)

    paginated = get_paginated_format_v2(qs, page_size, page)
    paginated["results"] = AdminShortLinkClickSerializer(paginated["results"], many=True).data

    source_qs = (
        ShortLinkClick.objects.exclude(source__isnull=True)
        .exclude(source="")
        .order_by("source")
        .values_list("source", flat=True)
        .distinct()
    )
    paginated["source_options"] = [{"label": src, "value": src} for src in source_qs]

    return Response(paginated)


api_urls = [
    path("links/<str:tag>/", short_link_click, name="short_link_click"),
    path("links/<str:tag>", short_link_click, name="short_link_click2"),
]
