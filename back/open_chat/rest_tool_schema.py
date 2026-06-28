import logging
import warnings
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from drf_spectacular.generators import SchemaGenerator

from open_chat.helpers import _normalize_base_url_for_open_chat_tool

API_HOST_INIT_FIELD = "api_host"

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


_LOCAL_TOOL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "host.docker.internal"})


def allow_local_tool_hosts(builder: Any, hostname: str) -> Any:
    """Allow Open Chat REST tool callbacks from common local dev hostnames."""
    host = hostname.strip().lower()
    if host in _LOCAL_TOOL_HOSTNAMES:
        allowed = sorted({host, *_LOCAL_TOOL_HOSTNAMES})
        return builder.allow_hosts(*allowed).allow_private_ips(True)
    return builder.allow_hosts(host).allow_private_ips(False)


_SESSION_AUTH_HEADER_NAMES = frozenset({"Cookie", "X-CSRFToken"})


def _collect_openapi_parameters(openapi_doc: dict[str, Any], path: str, method: str) -> list[dict[str, Any]]:
    path_item = openapi_doc.get("paths", {}).get(path, {})
    if not isinstance(path_item, dict):
        return []
    operation = path_item.get(method.strip().lower(), {})
    if not isinstance(operation, dict):
        operation = {}
    params: list[dict[str, Any]] = []
    if isinstance(path_item.get("parameters"), list):
        params.extend(path_item["parameters"])
    if isinstance(operation.get("parameters"), list):
        params.extend(operation["parameters"])
    return params


def bind_openapi_call_params(
    builder: Any,
    openapi_doc: dict[str, Any],
    path: str,
    method: str,
) -> Any:
    """Auto bind_call for every OpenAPI path/query parameter (session headers are init-bound separately)."""
    seen: set[str] = set()
    for param in _collect_openapi_parameters(openapi_doc, path, method):
        if not isinstance(param, dict):
            continue
        param_name = str(param.get("name", "")).strip()
        param_in = str(param.get("in", "")).strip()
        if not param_name or param_name in seen:
            continue
        if param_in == "header":
            continue
        seen.add(param_name)
        if param_in == "path":
            builder = builder.bind_call(param_name).to_path(param_name)
        elif param_in == "query":
            builder = builder.bind_call(param_name).to_query(param_name)
    return builder
