from django.db import models

from .user import User


class IssueReport(models.Model):
    """
    Stores reported issues made by users
    """

    reporting_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reported_issues")
    reported_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="issues_reported_against"
    )

    kind = models.CharField(max_length=255)
    keywords = models.JSONField(default=list)
    reason = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"IssueReport {self.id}: {self.kind} by {self.reporting_user.hash[:8]}"
