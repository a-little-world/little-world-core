"""Shared lobby instance resolution for analytics, management, and tasks APIs."""

from __future__ import annotations

from uuid import UUID

from django.utils import timezone

from video.models import RandomCallLobby


class InvalidLobbyUuid(ValueError):
    """Raised when lobby_uuid is present but not a valid UUID string."""


def resolve_lobby_instance(lobby_name: str, lobby_uuid=None) -> RandomCallLobby | None:
    """
    Resolve a lobby instance for admin/analytics views.

    - If *lobby_uuid* is set: return that instance only when it also matches *lobby_name*.
    - Otherwise: active lobby for *lobby_name*, or the most recent finished one.

    Raises InvalidLobbyUuid when *lobby_uuid* is not a valid UUID.
    """
    if lobby_uuid:
        try:
            parsed_uuid = UUID(str(lobby_uuid))
        except ValueError as exc:
            raise InvalidLobbyUuid("Invalid lobby_uuid") from exc
        return RandomCallLobby.objects.filter(uuid=parsed_uuid, name=lobby_name).first()

    now = timezone.now()
    lobby = (
        RandomCallLobby.objects.filter(
            name=lobby_name,
            start_time__lte=now,
            end_time__gte=now,
        )
        .order_by("-id")
        .first()
    )
    if lobby is None:
        lobby = (
            RandomCallLobby.objects.filter(
                name=lobby_name,
                end_time__lt=now,
            )
            .order_by("-end_time")
            .first()
        )
    return lobby
