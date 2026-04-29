from urllib.parse import urlparse

from back.utils import get_options_serializer
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.helpers.path_rename import PathRename
from management.models.banner import Banner


def _apply_background_image_upload(request, banner: Banner) -> None:
    """Persist optional background_image file and set background CSS url(...) (max 255 chars)."""
    uploaded = request.FILES.get("background_image")
    if not uploaded:
        return
    renamer = PathRename("banner_backgrounds/")
    relative_path = renamer(banner, uploaded.name)
    saved_path = default_storage.save(relative_path, uploaded)
    media_url = default_storage.url(saved_path)
    if media_url.startswith("http"):
        media_url = urlparse(media_url).path or media_url
    css_value = f"url({media_url})"
    banner.background = css_value[:255]
    banner.save(update_fields=["background"])


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
            "cta_2_url",
            "cta_2_text",
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
        _apply_background_image_upload(request, banner)
        return Response(AdminBannerSerializer(banner).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_banner_detail(request, pk: int):
    banner = get_object_or_404(Banner, pk=pk)

    if request.method == "GET":
        return Response(AdminBannerSerializer(banner).data)

    partial = request.method == "PATCH"
    serializer = AdminBannerSerializer(banner, data=request.data, partial=partial)
    if serializer.is_valid():
        updated = serializer.save()
        _apply_background_image_upload(request, updated)
        return Response(AdminBannerSerializer(updated).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
