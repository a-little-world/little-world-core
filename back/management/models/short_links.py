from django.db import models
from rest_framework import serializers


def _default_example_tracking_cookie():
    """Legacy default kept for migration 0107 imports only."""
    return [{"name": "lw-company", "value": "accenture"}]


class ShortLink(models.Model):
    tag = models.CharField(max_length=255, unique=True)
    url = models.URLField(max_length=2048)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    tracking_cookies_enabled = models.BooleanField(default=False)
    tracking_cookies = models.JSONField(null=True, blank=True)

    register_at_app_root = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.tag} -> {self.url}"


class TrackingCookieEntrySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, allow_blank=True)
    value = serializers.CharField(max_length=2048, allow_blank=True)


class AdminShortLinkSerializer(serializers.ModelSerializer):
    """Admin CRUD; `tag` is only writable when creating a new short link."""

    click_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = ShortLink
        fields = [
            "id",
            "tag",
            "url",
            "tracking_cookies_enabled",
            "tracking_cookies",
            "register_at_app_root",
            "created_at",
            "updated_at",
            "archived_at",
            "click_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "archived_at", "click_count"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields["tag"].read_only = True

    def validate_tracking_cookies(self, value):
        if value is None:
            return None
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list of cookie objects.")
        serializer = TrackingCookieEntrySerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        cleaned = []
        for row in serializer.validated_data:
            name = (row.get("name") or "").strip()
            value_str = (row.get("value") or "").strip()
            if not name and not value_str:
                continue
            if not name or not value_str:
                raise serializers.ValidationError("Each tracking cookie row needs both a name and a value.")
            cleaned.append({"name": name, "value": value_str})
        return cleaned if cleaned else None


class ShortLinkClick(models.Model):
    user = models.ForeignKey("management.User", on_delete=models.CASCADE, null=True, blank=True)
    short_link = models.ForeignKey(ShortLink, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    source = models.TextField(default="none")

    def __str__(self):
        return f"{self.user.email if self.user else 'Anonymous'} -> {self.short_link.tag}"
