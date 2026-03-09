import uuid

from django.db import models
from push_notifications.models import GCMDevice


class MobileDevice(GCMDevice):
    install_id = models.UUIDField(
        verbose_name=("Installation ID"),
        help_text=("Unique ID per installation on a mobile device"),
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        editable=False,
    )

    platform = models.CharField(
        verbose_name=("Platform"),
        help_text=("Platform of the device (iOS, android, ...)"),
        null=True,
        blank=True,
        editable=True,
        max_length=256,
    )

    model_name = models.CharField(
        verbose_name=("Device model"),
        help_text=("The model of the device (iPhone 17 Pro, Google Pixel 10 Pro, ...)"),
        null=True,
        blank=True,
        editable=True,
        max_length=256,
    )

    class Meta:
        verbose_name = "Mobile device"
