from django.db import models


class ManagementAccessGrant(models.Model):
    """
    Explicit ACL row for manager -> managed user access.
    This is intended to replace State.managed_users over time.
    """

    manager = models.ForeignKey(
        "management.User",
        on_delete=models.CASCADE,
        related_name="management_accesses_granted",
    )
    managed_user = models.ForeignKey(
        "management.User",
        on_delete=models.CASCADE,
        related_name="management_accesses_received",
    )
    granted_by = models.ForeignKey(
        "management.User",
        on_delete=models.SET_NULL,
        related_name="management_accesses_created",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["manager", "managed_user"],
                name="unique_manager_managed_user_access",
            )
        ]
        indexes = [
            models.Index(fields=["manager", "is_active"], name="mgmt_access_mgr_active_idx"),
            models.Index(fields=["managed_user", "is_active"], name="mgmt_access_usr_active_idx"),
        ]

    def __str__(self):
        return f"{self.manager_id}->{self.managed_user_id} active={self.is_active}"
