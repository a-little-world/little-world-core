import copy
import logging
import warnings
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import urlparse

from client import RESTToolBuilder
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
def _spectacular_schema() -> dict[str, Any]:
    return _generate_spectacular_schema()


def _collect_component_schemas(
    schema: dict[str, Any],
    schema_names: tuple[str, ...],
) -> dict[str, Any]:
    all_schemas = schema.get("components", {}).get("schemas", {})
    collected = {name: copy.deepcopy(all_schemas[name]) for name in schema_names if name in all_schemas}
    if not collected:
        return {}
    return {"schemas": collected}


def build_openapi_document_template(
    *,
    path: str,
    method: Literal["get", "post", "put", "patch", "delete"],
    info_title: str,
    extra_parameters: list[dict[str, Any]] | None = None,
    request_body: dict[str, Any] | None = None,
    component_schema_names: tuple[str, ...] = (),
) -> tuple[str, dict[str, Any]]:
    schema = _spectacular_schema()
    path_item = schema.get("paths", {}).get(path)
    if path_item is None:
        raise RuntimeError(f"OpenAPI path not found: {path}")

    operation = copy.deepcopy(path_item.get(method, {}))
    operation_id = operation.get("operationId")
    if not operation_id:
        raise RuntimeError(f"OpenAPI operation missing operationId: {path} {method}")

    operation["parameters"] = list(operation.get("parameters") or [])
    if extra_parameters:
        operation["parameters"].extend(copy.deepcopy(extra_parameters))
    if request_body is not None:
        operation["requestBody"] = copy.deepcopy(request_body)

    components = _collect_component_schemas(schema, component_schema_names)
    openapi_doc = {
        "openapi": schema.get("openapi", "3.0.3"),
        "info": {"title": info_title, "version": "1.0.0"},
        "paths": {path: {method: operation}},
        "components": components,
    }
    return operation_id, openapi_doc


def default_api_host() -> str:
    return _normalize_base_url_for_open_chat_tool(settings.BASE_URL).rstrip("/")


def openapi_doc_with_server(
    *,
    path: str,
    method: Literal["get", "post", "put", "patch", "delete"],
    info_title: str,
    extra_parameters: list[dict[str, Any]] | None = None,
    request_body: dict[str, Any] | None = None,
    component_schema_names: tuple[str, ...] = (),
    api_host: str | None = None,
) -> tuple[str, dict[str, Any], str]:
    operation_id, openapi_doc = build_openapi_document_template(
        path=path,
        method=method,
        info_title=info_title,
        extra_parameters=extra_parameters,
        request_body=request_body,
        component_schema_names=component_schema_names,
    )
    resolved_api_host = (api_host or default_api_host()).rstrip("/")
    openapi_doc["servers"] = [{"url": resolved_api_host}]
    hostname = urlparse(resolved_api_host).hostname
    if not hostname:
        raise ValueError(f"Invalid api host: {resolved_api_host!r}")
    return operation_id, openapi_doc, hostname


def with_session_auth(builder: RESTToolBuilder) -> RESTToolBuilder:
    return builder.bind_init("cookie_header").to_header("Cookie").bind_init("csrf_token").to_header("X-CSRFToken")


def with_hostname_policy(builder: RESTToolBuilder, hostname: str) -> RESTToolBuilder:
    return builder.allow_hosts(hostname).allow_private_ips(
        hostname.lower() in {"localhost", "host.docker.internal", "127.0.0.1"}
    )
