import uuid
from datetime import timedelta
from typing import Any

from django.db import models
from django.utils import timezone
from push_notifications.models import GCMDevice, GCMDeviceManager, GCMDeviceQuerySet

ACTIVE_SESSION_TIMEOUT = timedelta(seconds=10)


class MobileDeviceQuerySet(GCMDeviceQuerySet):
    def send_message(self, message: Any, **kwargs: Any) -> Any:
        return super().send_message(message, **kwargs)

    def online(self) -> "MobileDeviceQuerySet":
        return self.filter(session_active_at__gte=timezone.now() - ACTIVE_SESSION_TIMEOUT)


class MobileDeviceManager(GCMDeviceManager):
    def get_queryset(self) -> MobileDeviceQuerySet:
        return MobileDeviceQuerySet(self.model)

    def filter(self, *args: Any, **kwargs: Any) -> MobileDeviceQuerySet:
        return self.get_queryset().filter(*args, **kwargs)

    def none(self) -> MobileDeviceQuerySet:
        return self.get_queryset().none()


# Collection of devices with push notification capabilities
# Also includes web browsers on desktop devices
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

    session_active_at = models.DateTimeField(
        verbose_name=("Session active at"),
        help_text=("Last heartbeat of an open app session on this device, null while no session is open"),
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Mobile device"

    @classmethod
    def session_opened(cls, user, install_id):
        cls.objects.filter(user=user, install_id=install_id).update(session_active_at=timezone.now())

    @classmethod
    def session_closed(cls, user, install_id):
        cls.objects.filter(user=user, install_id=install_id).update(session_active_at=None)
