from django.db import models

from back import utils

from .user import User


class HelpMessage(models.Model):
    """
    Stores help messages and issue reports sent by users
    """

    class KindChoices(models.TextChoices):
        GENERAL = "general", "General"
        TECHNICAL = "technical", "Technical"
        REPORT_USER = "report_user", "Report User"
        CALL_QUALITY = "call_quality", "Call Quality"
        REPORT_PARTNER = "report_partner", "Report Partner"

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    hash = models.CharField(max_length=100, blank=True, unique=True, default=utils._double_uuid)  # type: ignore

    attachment1 = models.BinaryField(blank=True, null=True)
    attachment2 = models.BinaryField(blank=True, null=True)
    attachment3 = models.BinaryField(blank=True, null=True)

    message = models.TextField()

    # Fields for issue reporting functionality
    kind = models.CharField(max_length=255, choices=KindChoices.choices, default=KindChoices.GENERAL)
    keywords = models.JSONField(default=list, blank=True)
    reported_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="issues_reported_against"
    )
    origin = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
