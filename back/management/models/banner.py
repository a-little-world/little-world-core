from django.db import models
from django.utils.translation import gettext_lazy as _

class Banner(models.Model):
    name = models.CharField(
        max_length=255,
        help_text=_("Internal name for the banner")
    )

    active = models.BooleanField(
        default=True,
        help_text=_("Whether the banner is currently active")
    )
    
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Heading text")
    )

    text = models.TextField(
        blank=True,
        help_text=_("Main text content")
    )

    cta_1_url = models.URLField(
        blank=True,
        help_text=_("Cta 1 URL")
    )

    cta_1_text = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Cta 1 text")
    )

    cta_2_url = models.URLField(
        blank=True,
        help_text=_("Cta 2 URL")
    )

    cta_2_text = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Cta 2 text")
    )

    image_url = models.URLField(
        blank=True,
        help_text=_("Image URL")
    )

    image_alt = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Image alt text")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Banner")
        verbose_name_plural = _("Banners")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
    