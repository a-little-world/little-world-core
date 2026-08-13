import uuid

from asgiref.testing import ApplicationCommunicator
from channels.db import database_sync_to_async
from chat.consumers.core import CoreConsumer
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from management.models.mobile_device import ACTIVE_SESSION_TIMEOUT
from management.models.user import MobileDevice
from management.tests.helpers import register_user


def create_device(user, registration_id, platform, session_active_at=None):
    return MobileDevice.objects.create(
        user=user,
        registration_id=registration_id,
        install_id=uuid.uuid4(),
        platform=platform,
        active=True,
        session_active_at=session_active_at,
    )


class PushActiveSessionRoutingTests(TestCase):
    def setUp(self):
        self.user = register_user()
        self.browser = create_device(self.user, "browser-token", "web")
        self.phone = create_device(self.user, "phone-token", "android")
        self.tablet = create_device(self.user, "tablet-token", "ios")

    def _devices(self):
        return set(self.user.push_devices().values_list("registration_id", flat=True))

    def _open_session(self, device, age=None):
        device.session_active_at = timezone.now() - age if age else timezone.now()
        device.save()

    def test_without_any_open_session_all_devices_are_notified(self):
        self.assertEqual(self._devices(), {"browser-token", "phone-token", "tablet-token"})

    def test_only_the_device_with_an_open_session_is_notified(self):
        self._open_session(self.phone)
        self.assertEqual(self._devices(), {"phone-token"})

    def test_every_device_with_an_open_session_is_notified(self):
        self._open_session(self.phone)
        self._open_session(self.browser)
        self.assertEqual(self._devices(), {"browser-token", "phone-token"})

    def test_sessions_that_stopped_heartbeating_are_ignored(self):
        self._open_session(self.phone, age=2 * ACTIVE_SESSION_TIMEOUT)
        self.assertEqual(self._devices(), {"browser-token", "phone-token", "tablet-token"})

    def test_opted_out_user_is_never_notified(self):
        self._open_session(self.phone)
        self.user.profile.push_notifications_enabled = False
        self.user.profile.save()
        self.assertEqual(self._devices(), set())


class PushSessionWebsocketTests(TransactionTestCase):
    """The session state the routing above relies on is written by the core websocket."""

    async def test_websocket_opens_and_closes_the_session_of_its_device(self):
        user = await self._user()
        device = await self._device(user)

        connection = await self._connect(user, device)
        self.assertIsNotNone(await self._session_active_at(device))

        self.assertEqual(await self._ping(connection), "pong")

        await self._disconnect(connection)
        self.assertIsNone(await self._session_active_at(device))

    async def test_heartbeat_keeps_a_stale_session_open(self):
        user = await self._user()
        device = await self._device(user, session_active_at=timezone.now() - 10 * ACTIVE_SESSION_TIMEOUT)

        connection = await self._connect(user, device)
        await self._ping(connection)

        fresh_since = timezone.now() - ACTIVE_SESSION_TIMEOUT
        self.assertGreater(await self._session_active_at(device), fresh_since)
        await self._disconnect(connection)

    async def _connect(self, user, device):
        connection = ApplicationCommunicator(
            CoreConsumer.as_asgi(),
            {
                "type": "websocket",
                "path": "/api/core/ws",
                "query_string": f"install_id={device.install_id}".encode(),
                "headers": [],
                "subprotocols": [],
                "user": user,
            },
        )
        await connection.send_input({"type": "websocket.connect"})
        self.assertEqual((await connection.receive_output())["type"], "websocket.accept")
        return connection

    @staticmethod
    async def _ping(connection):
        await connection.send_input({"type": "websocket.receive", "text": "ping"})
        return (await connection.receive_output())["text"]

    @staticmethod
    async def _disconnect(connection):
        await connection.send_input({"type": "websocket.disconnect", "code": 1000})
        await connection.wait()

    @staticmethod
    async def _user():
        return await database_sync_to_async(register_user)()

    @staticmethod
    async def _device(user, session_active_at=None):
        return await database_sync_to_async(create_device)(user, "phone-token", "android", session_active_at)

    @staticmethod
    async def _session_active_at(device):
        return await database_sync_to_async(
            lambda: MobileDevice.objects.get(pk=device.pk).session_active_at,
        )()
