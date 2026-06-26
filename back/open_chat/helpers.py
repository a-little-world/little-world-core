from importlib import import_module
from typing import Any, TypeVar
from urllib.parse import urlparse, urlunparse

from client import InteractionSession
from client.generated_api.types import Unset
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from management import controller
from management.models.user import User

FALLBACK_USER_MESSAGE = "Hallo"

_T = TypeVar("_T")


def value_or(value: "_T | Unset", default: _T) -> _T:
    """Return a typed client value, falling back to ``default`` when the field is ``UNSET``."""
    return default if isinstance(value, Unset) else value


def _tool_call_name(tool_call: Any) -> str:
    return str(tool_call.get("name") or "") if isinstance(tool_call, dict) else ""


def _create_session_and_csrf_for_user(user: User) -> tuple[str, str]:
    from django.middleware.csrf import _get_new_csrf_string

    session_engine = import_module(settings.SESSION_ENGINE)
    session = session_engine.SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return session.session_key, _get_new_csrf_string()


def _normalize_base_url_for_open_chat_tool(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.hostname != "localhost":
        return base_url

    port = f":{parsed.port}" if parsed.port else ""
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"

    normalized_netloc = f"{userinfo}host.docker.internal{port}"
    return urlunparse(parsed._replace(netloc=normalized_netloc))


def build_tool_session_context(actor: User) -> tuple[str, str, str]:
    """Create a Django session + CSRF token for ``actor`` and resolve the tool callback host."""
    session_id, csrf_token = _create_session_and_csrf_for_user(actor)
    api_host = _normalize_base_url_for_open_chat_tool(settings.BASE_URL).rstrip("/")
    return session_id, csrf_token, api_host


def interaction_called_tool(interaction: InteractionSession, tool_name: str) -> bool:
    page = interaction.messages(page=1, limit=200)
    for message in value_or(page.rows, []):
        if any(_tool_call_name(tc) == tool_name for tc in value_or(message.tool_calls, [])):
            return True
    return False


def resolve_open_chat_automation_task_creator_user() -> User | None:
    automation_user_email = (settings.OPEN_CHAT_AUTOMATION_USER_EMAIL or "").strip()
    created_by_user = User.objects.filter(email=automation_user_email).first() if automation_user_email else None
    if created_by_user is None:
        created_by_user = controller.create_open_chat_automation_user()
    return created_by_user
