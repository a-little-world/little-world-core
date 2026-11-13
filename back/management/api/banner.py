from uuid import uuid4

from back.utils import get_options_serializer
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.models.banner import Banner


def _truthy_flag(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def _apply_background_image_upload(request, banner: Banner) -> None:
    """Persist optional background_image file and set background CSS url(...) (max 255 chars).

    Uses a unique object key every upload so S3/MinIO Cache-Control does not serve a stale image
    at a reused path (PathRename with pk would overwrite the same key).
    """
    uploaded = request.FILES.get("background_image")
    if not uploaded:
        return
    ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else "png"
    # Keep extension short/safe for CSS url(...) within CharField max_length.
    ext = "".join(c for c in ext if c.isalnum())[:8] or "png"
    relative_path = f"banner_backgrounds/{banner.pk}_{uuid4().hex}.{ext}"
    saved_path = default_storage.save(relative_path, uploaded)
    media_url = default_storage.url(saved_path)
    css_value = f"url({media_url})"
    banner.background = css_value[:255]
    banner.save(update_fields=["background"])


def _apply_clear_flags(request, banner: Banner) -> Banner:
    """Clear banner image and/or background when clear_* flags are sent."""
    update_fields: list[str] = []

    if _truthy_flag(request.data.get("clear_image")):
        if banner.image:
            banner.image.delete(save=False)
        banner.image = ""
        update_fields.append("image")

    if _truthy_flag(request.data.get("clear_background")):
        banner.background = ""
        update_fields.append("background")

    if update_fields:
        banner.save(update_fields=update_fields)
    return banner


class AdminBannerSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    def get_options(self, obj):
        return get_options_serializer(self, obj)

    class Meta:
        model = Banner
        fields = [
            "id",
            "name",
            "active",
            "title",
            "text",
            "text_color",
            "background",
            "cta_1_url",
            "cta_1_text",
            "cta_1_color",
            "cta_2_url",
            "cta_2_text",
            "cta_2_color",
            "type",
            "image",
            "image_alt",
            "created_at",
            "updated_at",
            "activation_time",
            "expiration_time",
            "custom_filter",
            "filter_priority",
            "options",
        ]


@api_view(["GET", "POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_banners(request):
    if request.method == "GET":
        banners = Banner.objects.all().order_by("-created_at")
        return Response(AdminBannerSerializer(banners, many=True).data)

    serializer = AdminBannerSerializer(data=request.data)
    if serializer.is_valid():
        banner = serializer.save()
        _apply_clear_flags(request, banner)
        _apply_background_image_upload(request, banner)
        return Response(AdminBannerSerializer(banner).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_banner_detail(request, pk: int):
    banner = get_object_or_404(Banner, pk=pk)

    if request.method == "GET":
        return Response(AdminBannerSerializer(banner).data)

    if request.method == "DELETE":
        if banner.image:
            banner.image.delete(save=False)
        banner.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    partial = request.method == "PATCH"
    serializer = AdminBannerSerializer(banner, data=request.data, partial=partial)
    if serializer.is_valid():
        updated = serializer.save()
        # Clear flags run before upload so a new upload can replace a cleared field in one request.
        _apply_clear_flags(request, updated)
        _apply_background_image_upload(request, updated)
        return Response(AdminBannerSerializer(updated).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
