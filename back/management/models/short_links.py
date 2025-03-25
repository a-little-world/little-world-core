from django.db import models


class ShortLink(models.Model):
    tag = models.CharField(max_length=255)
    url = models.URLField(max_length=2048)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tag} -> {self.url}"

class ShortLinkClick(models.Model):
    user = models.ForeignKey("management.User", on_delete=models.CASCADE)
    short_link = models.ForeignKey(ShortLink, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} -> {self.short_link.tag}"
