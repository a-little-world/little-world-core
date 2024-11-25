from django.db import models
from django.utils.translation import gettext_lazy as _


class Banner(models.Model):
    # Generic fields
    name = models.CharField(
        max_length=255,
        help_text=_("Internal name for the banner")
    )
    active = models.BooleanField(
        default=True,
        help_text=_("Whether the banner is currently active")
    )
    
    # Learner specific fields
    learner_heading = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Heading text for learner users")
    )
    learner_text = models.TextField(
        blank=True,
        help_text=_("Main text content for learner users")
    )
    learner_button_url = models.URLField(
        blank=True,
        help_text=_("Button URL for learner users")
    )
    learner_button_text = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Button text for learner users")
    )
    learner_image_url = models.URLField(
        blank=True,
        help_text=_("Image URL for learner users")
    )
    learner_image_alt = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Image alt text for learner users")
    )
    
    # Volunteer specific fields
    volunteer_heading = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Heading text for volunteer users")
    )
    volunteer_text = models.TextField(
        blank=True,
        help_text=_("Main text content for volunteer users")
    )
    volunteer_button_url = models.URLField(
        blank=True,
        help_text=_("Button URL for volunteer users")
    )
    volunteer_button_text = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Button text for volunteer users")
    )
    volunteer_image_url = models.URLField(
        blank=True,
        help_text=_("Image URL for volunteer users")
    )
    volunteer_image_alt = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Image alt text for volunteer users")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Banner")
        verbose_name_plural = _("Banners")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_content_for_user_type(self, user_type):
        """
        Returns a dictionary containing all content fields for a specific user type
        """
        prefix = user_type.lower()
        return {
            'heading': getattr(self, f'{prefix}_heading'),
            'text': getattr(self, f'{prefix}_text'),
            'button_url': getattr(self, f'{prefix}_button_url'),
            'button_text': getattr(self, f'{prefix}_button_text'),
            'image_url': getattr(self, f'{prefix}_image_url'),
            'image_alt': getattr(self, f'{prefix}_image_alt'),
        }