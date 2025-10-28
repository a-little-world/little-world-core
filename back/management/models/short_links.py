from django.db import models


def _default_example_tracking_cookie():
    return [{"name": "lw-company", "value": "accenture"}]

class ShortLink(models.Model):
    tag = models.CharField(max_length=255)
    url = models.URLField(max_length=2048)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    tracking_cookies_enabled = models.BooleanField(default=False)
    tracking_cookies = models.JSONField(default=_default_example_tracking_cookie)

    register_at_app_root = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.tag} -> {self.url}"

class ShortLinkClick(models.Model):
    user = models.ForeignKey("management.User", on_delete=models.CASCADE, null=True, blank=True)
    short_link = models.ForeignKey(ShortLink, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    source = models.TextField(default="none")

    def __str__(self):
        return f"{self.user.email if self.user else 'Anonymous'} -> {self.short_link.tag}"