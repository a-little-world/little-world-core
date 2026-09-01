import uuid as uuid_lib
from importlib import import_module
from typing import Any, TypeVar
from urllib.parse import urlparse, urlunparse

from client import InteractionSession, OpenChatClient, PasswordAuth, TokenAuth
from client.generated_api.types import Unset
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from management import controller
from management.models.user import User

FALLBACK_USER_MESSAGE = "Hallo"

_T = TypeVar("_T")


def build_open_chat_client(configuration) -> OpenChatClient:
    """Build an authenticated OpenChatClient for server-side Open Chat calls.

    Prefer Bearer ``TokenAuth`` when ``open_chat_api_key`` looks like an access
    token; otherwise fall back to email/password login.

    The upstream client passes ``cookie_domain=<hostname>`` on password login.
    For Docker Compose hostnames (and some other hosts) that produces
    ``Domain=…`` cookies that httpx will not re-send, so login succeeds and
    ``/user/self`` then returns 403. Always use host-only cookies for this
    server-side client.
    """
    api_key = (configuration.open_chat_api_key or "").strip()
    open_chat_user = (configuration.open_chat_user or "").strip()

    # Open Chat originally issued UUID access tokens and now issues prefixed
    # ``ocat_`` tokens. Local/dev can still store a password here.
    use_token_auth = bool(api_key) and _looks_like_open_chat_access_token(api_key)

    if use_token_auth:
        client = OpenChatClient(
            base_url=configuration.open_chat_host,
            auth=TokenAuth(token=api_key),
        )
    else:
        client = OpenChatClient(
            base_url=configuration.open_chat_host,
            auth=PasswordAuth(email=open_chat_user, password=api_key),
        )

    client._cookie_domain = lambda: ""  # type: ignore[method-assign]
    return client


def _looks_like_open_chat_access_token(value: str) -> bool:
    if value.startswith(("ocat_", "oc_")):
        return True
    try:
        parsed = uuid_lib.UUID(value)
    except ValueError:
        return False
    return str(parsed) == value.lower()


def exchange_open_chat_browser_token(
    configuration,
    *,
    scopes: list[str],
    ttl_seconds: int = 900,
    label: str = "little-world-admin",
) -> dict[str, Any]:
    """Exchange a stored Open Chat credential for an ephemeral browser token."""
    client = build_open_chat_client(configuration)
    client.login()
    response = client._api.get_httpx_client().post(  # type: ignore[attr-defined]
        "/api/v1/user/browser-token",
        json={
            "scopes": scopes,
            "ttl_seconds": ttl_seconds,
            "label": label,
        },
        timeout=10.0,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"browser-token exchange returned HTTP {response.status_code}")

    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise RuntimeError("browser-token exchange returned an invalid response")
    return payload


def resolve_open_chat_frontend_host(configuration=None) -> str:
    """Return the browser-facing Open Chat origin.

    Prefers ``DJ_DEFAULT_OPEN_CHAT_FRONTEND_HOST`` when set; otherwise uses the
    configuration's ``open_chat_host`` (server-side / Docker DNS host).
    """
    override = (getattr(settings, "DEFAULT_OPEN_CHAT_FRONTEND_HOST", None) or "").strip()
    if override:
        return override.rstrip("/")
    if configuration is not None:
        return str(configuration.open_chat_host).rstrip("/")
    return str(settings.DEFAULT_OPEN_CHAT_CONFIGURATION["open_chat_host"]).rstrip("/")


def rewrite_open_chat_url_for_browser(raw_url: str | None, configuration=None) -> str | None:
    """Rewrite an Open Chat URL's origin for browser/iframe use."""
    if not raw_url:
        return raw_url
    frontend_host = resolve_open_chat_frontend_host(configuration)
    try:
        parsed = urlparse(raw_url)
        frontend = urlparse(frontend_host if "://" in frontend_host else f"http://{frontend_host}")
    except ValueError:
        return raw_url
    if not parsed.scheme or not parsed.netloc:
        return raw_url
    frontend_netloc = frontend.netloc or frontend.path
    if not frontend_netloc:
        return raw_url
    return urlunparse(
        parsed._replace(
            scheme=frontend.scheme or parsed.scheme or "http",
            netloc=frontend_netloc,
        )
    )


def little_world_panel_base_url() -> str:
    """Browser-facing origin for admin panel links embedded in chat messages."""
    return str(settings.BASE_URL).rstrip("/")


def build_chat_text_markup_hint(base_url: str | None = None) -> str:
    origin = (base_url or little_world_panel_base_url()).rstrip("/")
    return f"""
User-visible message formatting (Little World chat text renderer):
- Links: ALWAYS use <a {{"href": "URL", "target": "_blank"}}>link label</a>. Never paste bare URLs — they often fail to render as clickable links (especially on localhost).
- Emphasis: <bold>text</bold>, <highlight>text</highlight>
Little World admin panel base URL: {origin}
When linking to management panel pages, use absolute URLs with this origin inside the href attribute (never relative paths alone).
When a list link includes page_size, never set page_size below 20 (use page_size=20 or omit page_size).
Admin panel link examples (use this exact syntax in user-visible replies):
- Single user: <a {{"href": "{origin}/matching/user/22", "target": "_blank"}}>View user profile</a>
- User chat tab: <a {{"href": "{origin}/matching/user/22?tab=chat", "target": "_blank"}}>Open user chat</a>
- Onboarded learners list: <a {{"href": "{origin}/matching/users/?profile__user_type=learner&state__is_onboarded=true&page_size=20", "target": "_blank"}}>View onboarded learners</a>
- Filtered user list: <a {{"href": "{origin}/matching/users/?list=all&page_size=20", "target": "_blank"}}>Open users</a>
- Single match: <a {{"href": "{origin}/matching/match/{{match_id}}?tab=overview", "target": "_blank"}}>View match</a>
- Filtered match list: <a {{"href": "{origin}/matching/matches/?list=match_journey_v2__active&page_size=20", "target": "_blank"}}>Open matches</a>
Path rules: use /matching/user/{{numeric_id}} for one user (never /matching/users/?search=… when you know the id). Use /matching/users/?… only for cohort lists.
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
