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


def little_world_panel_base_url() -> str:
    """Browser-facing origin for admin panel links embedded in chat messages."""
    return str(settings.BASE_URL).rstrip("/")


def build_chat_text_markup_hint(base_url: str | None = None) -> str:
    origin = (base_url or little_world_panel_base_url()).rstrip("/")
    return f"""
User-visible message formatting (Little World chat text renderer):
- Links: <a {{"href": "https://example.com/path"}}>link label</a> or bare https:// URLs
- Emphasis: <bold>text</bold>, <highlight>text</highlight>
Little World admin panel base URL: {origin}
When linking to management panel pages, always use absolute URLs with this origin (never relative paths alone).
Single user (use numeric id from API): {origin}/matching/user/22 or {origin}/matching/user/22?tab=chat
Filtered user list (cohorts only): {origin}/matching/users/?list=all&page_size=5
Single match: {origin}/matching/match/{{match_id}}?tab=overview
Filtered match list: {origin}/matching/matches/?list=match_journey_v2__active&page_size=5
Never use /matching/users/?search=… when you already know the user's numeric id — use /matching/user/{{id}} instead.
""".strip()


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


_LOCAL_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1"})


def _normalize_base_url_for_open_chat_tool(base_url: str) -> str:
    """Rewrite loopback hosts so Open Chat (in Docker) can reach the Django backend."""
    parsed = urlparse(base_url)
    if parsed.hostname not in _LOCAL_LOOPBACK_HOSTNAMES:
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


def open_chat_tool_api_host() -> str:
    """Resolve the api_host Open Chat uses when calling Django REST tools."""
    override = getattr(settings, "OPEN_CHAT_TOOL_API_HOST", None)
    if override:
        return _normalize_base_url_for_open_chat_tool(str(override).rstrip("/"))
    return _normalize_base_url_for_open_chat_tool(settings.BASE_URL).rstrip("/")


def build_tool_session_context(actor: User) -> tuple[str, str, str]:
    """Create a Django session + CSRF token for ``actor`` and resolve the tool callback host."""
    session_id, csrf_token = _create_session_and_csrf_for_user(actor)
    return session_id, csrf_token, open_chat_tool_api_host()


def build_session_tool_init_payload(
    *,
    api_host: str,
    session_id: str,
    csrf_token: str,
    **fields: str,
) -> dict[str, str]:
    return {
        "api_host": _normalize_base_url_for_open_chat_tool(api_host).rstrip("/"),
        "cookie_header": f"sessionid={session_id}; csrftoken={csrf_token}",
        "csrf_token": csrf_token,
        **fields,
    }


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
