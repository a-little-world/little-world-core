import uuid
from typing import Any

from django.db import models
from push_notifications.models import GCMDevice, GCMDeviceManager, GCMDeviceQuerySet


class MobileDeviceQuerySet(GCMDeviceQuerySet):
    def send_message(self, message: Any, **kwargs: Any) -> Any:
        return super().send_message(message, **kwargs)


class MobileDeviceManager(GCMDeviceManager):
    def get_queryset(self) -> MobileDeviceQuerySet:
        return MobileDeviceQuerySet(self.model)

    def filter(self, *args: Any, **kwargs: Any) -> MobileDeviceQuerySet:
        return self.get_queryset().filter(*args, **kwargs)

    def none(self) -> MobileDeviceQuerySet:
        return self.get_queryset().none()


class MobileDevice(GCMDevice):
    objects: MobileDeviceManager = MobileDeviceManager()

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
