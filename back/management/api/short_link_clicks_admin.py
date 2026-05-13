from datetime import date, datetime, time, timedelta

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import get_paginated_format_v2
from management.models.short_links import ShortLinkClick


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
