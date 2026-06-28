import logging
import warnings
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from drf_spectacular.generators import SchemaGenerator

from open_chat.helpers import _normalize_base_url_for_open_chat_tool

SESSION_AUTH_HEADER_PARAMS = [
    {
        "in": "header",
        "name": "Cookie",
        "required": True,
        "schema": {"type": "string"},
        "description": "Session cookie header, e.g. sessionid=...; csrftoken=...",
    },
    {
        "in": "header",
        "name": "X-CSRFToken",
        "required": True,
        "schema": {"type": "string"},
        "description": "CSRF token matching the session cookie.",
    },
]


def _generate_spectacular_schema() -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", module="drf_spectacular")
        logging.getLogger("drf_spectacular").setLevel(logging.ERROR)
        return SchemaGenerator().get_schema(request=None, public=True)


@lru_cache(maxsize=1)
def spectacular_schema() -> dict[str, Any]:
    return _generate_spectacular_schema()


def default_api_host() -> str:
    return _normalize_base_url_for_open_chat_tool(settings.BASE_URL).rstrip("/")


def resolve_api_host(api_host: str | None = None) -> tuple[str, str]:
    resolved = (api_host or default_api_host()).rstrip("/")
    hostname = urlparse(resolved).hostname
    if not hostname:
        raise ValueError(f"Invalid api host: {resolved!r}")
    return resolved, hostname
