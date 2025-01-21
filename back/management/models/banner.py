from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from management.helpers import PathRename
from colorfield.fields import ColorField

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

    text_color = ColorField(default='#000000')

    background = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Background color or image. Images can be set by the following: url(PATH_OF_IMAGE). Gradients can be set by the following: linear-gradient(#e66465, #9198e5).")
    )

    cta_1_url = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Cta 1 URL")
    )

    cta_1_text = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Cta 1 text")
    )

    cta_2_url = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Cta 2 URL")
    )

    cta_2_text = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Cta 2 text")
    )

    image = models.ImageField(upload_to=PathRename("banner_pics/"), blank=True, help_text=_("Upload landscape-oriented banner images with a 16:9 aspect ratio, minimum resolution of 1920 x 1080 pixels, and maximum file size of 2 MB. Use high-quality JPEG or PNG files, ensuring the image is sharp, clear, and allows for text overlay. Keep critical content centered to accommodate potential cropping across different devices."))

    image_alt = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Image alt text")
    )
    
    class BannerType(models.TextChoices):
        small = "small", "Small"
        large = "large", "Large"

    type = models.CharField(
        max_length=255,
        default=BannerType.small,
        choices=BannerType.choices,
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Banner")
        verbose_name_plural = _("Banners")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class BannerSerializer(serializers.ModelSerializer):
    """
    Serializer for the Banner model to convert it to a dictionary
    """
    class Meta:
        model = Banner
        fields = [
            'id', 
            'name', 
            'active', 
            'title',
            'text',
            'text_color', 
            'background',
            'cta_1_url', 
            'cta_1_text', 
            'cta_2_url', 
            'cta_2_text', 
            'type',
            'image', 
            'image_alt',
            'created_at',
            'updated_at'
        ]

    def to_representation(self, instance):
        """
        Custom representation method to handle any specific serialization requirements
        """
        rep = super().to_representation(instance)
        return rep
