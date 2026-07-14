"""Build compact JSON response examples from drf-spectacular OpenAPI schemas."""

from __future__ import annotations

import json
from typing import Any

_REF_PREFIX = "#/components/schemas/"
_SUCCESS_RESPONSE_CODES = ("200", "201", "204", "default")
_JSON_MEDIA_TYPES = (
    "application/json",
    "text/json",
    "application/*+json",
)


_PRIORITY_OBJECT_PROPERTIES = (
    "results",
    "filters",
    "lists",
    "items_total",
    "page_size",
    "pages_total",
    "count",
    "chat",
    "messages",
)


def describe_openapi_response_example(
    schema_doc: dict[str, Any],
    *,
    path: str,
    method: str = "get",
    max_length: int = 1500,
    fallback: Any | None = None,
    trust_example: Any | None = None,
) -> str | None:
    validator = trust_example or (lambda _path, _candidate: True)
    example = extract_openapi_response_example(
        schema_doc,
        path=path,
        method=method,
        trust_example=validator,
    )
    if example is not None and validator(path, example):
        return format_openapi_response_example(example, max_length=max_length)
    if fallback is not None:
        return format_openapi_response_example(fallback, max_length=max_length)
    if example is not None:
        return format_openapi_response_example(example, max_length=max_length)
    return None


def append_output_example_to_description(description: str, example_text: str | None) -> str:
    if not example_text:
        return description
    return f"{description.rstrip()}\n\nExample JSON response:\n{example_text}"


def extract_openapi_response_example(
    schema_doc: dict[str, Any],
    *,
    path: str,
    method: str = "get",
    trust_example: Any | None = None,
) -> Any | None:
    operation = _get_operation(schema_doc, path, method)
    if operation is None:
        return None

    response = _pick_success_response(operation.get("responses", {}))
    if response is None:
        return None

    explicit = _extract_explicit_example(response, trust_example=trust_example, path=path)
    if explicit is not None:
        return explicit

    content_schema = _extract_response_content_schema(response)
    if content_schema is None:
        return None

    components = schema_doc.get("components", {})
    return _sample_json_schema(content_schema, components)


def format_openapi_response_example(example: Any, *, max_length: int = 1500) -> str:
    rendered = json.dumps(example, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(rendered) <= max_length:
        return rendered
    return f"{rendered[: max_length - 3]}..."


def _get_operation(schema_doc: dict[str, Any], path: str, method: str) -> dict[str, Any] | None:
    path_item = schema_doc.get("paths", {}).get(path)
    if not isinstance(path_item, dict):
        return None
    operation = path_item.get(method.strip().lower())
    return operation if isinstance(operation, dict) else None


def _pick_success_response(responses: Any) -> dict[str, Any] | None:
    if not isinstance(responses, dict):
        return None
    for status_code in _SUCCESS_RESPONSE_CODES:
        response = responses.get(status_code)
        if isinstance(response, dict):
            return response
    return None


def _extract_explicit_example(
    response: dict[str, Any],
    *,
    trust_example: Any | None = None,
    path: str = "",
) -> Any | None:
    if "example" in response:
        candidate = response["example"]
        if trust_example is None or trust_example(path, candidate):
            return candidate

    content = response.get("content")
    if not isinstance(content, dict):
        return None

    for media_type in _JSON_MEDIA_TYPES:
        media = content.get(media_type)
        if not isinstance(media, dict):
            continue
        if "example" in media:
            candidate = media["example"]
            if trust_example is None or trust_example(path, candidate):
                return candidate
        examples = media.get("examples")
        if isinstance(examples, dict):
            fallback: Any | None = None
            for example_entry in examples.values():
                if not isinstance(example_entry, dict) or "value" not in example_entry:
                    continue
                candidate = example_entry["value"]
                fallback = candidate
                if trust_example is None or trust_example(path, candidate):
                    return candidate
            if fallback is not None and trust_example is None:
                return fallback
    for media in content.values():
        if isinstance(media, dict):
            if "example" in media:
                candidate = media["example"]
                if trust_example is None or trust_example(path, candidate):
                    return candidate
    return None


def _extract_response_content_schema(response: dict[str, Any]) -> dict[str, Any] | None:
    content = response.get("content")
    if not isinstance(content, dict):
        return None

    for media_type in _JSON_MEDIA_TYPES:
        media = content.get(media_type)
        if isinstance(media, dict):
            schema = media.get("schema")
            if isinstance(schema, dict):
                return schema

    for media in content.values():
        if isinstance(media, dict):
            schema = media.get("schema")
            if isinstance(schema, dict):
                return schema
    return None


def _resolve_schema_ref(ref: str, components: dict[str, Any]) -> dict[str, Any] | None:
    if not ref.startswith(_REF_PREFIX):
        return None
    schema_name = ref[len(_REF_PREFIX) :]
    schemas = components.get("schemas", {})
    if not isinstance(schemas, dict):
        return None
    schema = schemas.get(schema_name)
    return schema if isinstance(schema, dict) else None


def _sample_json_schema(
    schema: dict[str, Any],
    components: dict[str, Any],
    *,
    depth: int = 0,
    max_depth: int = 5,
    array_items: int = 1,
    object_properties: int = 8,
) -> Any:
    if depth > max_depth:
        return "..."

    if "example" in schema:
        return schema["example"]

    if "$ref" in schema:
        resolved = _resolve_schema_ref(str(schema["$ref"]), components)
        if resolved is None:
            return {}
        return _sample_json_schema(
            resolved,
            components,
            depth=depth,
            max_depth=max_depth,
            array_items=array_items,
            object_properties=object_properties,
        )

    if "allOf" in schema and isinstance(schema["allOf"], list):
        merged: dict[str, Any] = {}
        for part in schema["allOf"]:
            if not isinstance(part, dict):
                continue
            sampled = _sample_json_schema(
                part,
                components,
                depth=depth + 1,
                max_depth=max_depth,
                array_items=array_items,
                object_properties=object_properties,
            )
            if isinstance(sampled, dict):
                merged.update(sampled)
        if merged:
            return merged

    for composite_key in ("oneOf", "anyOf"):
        options = schema.get(composite_key)
        if isinstance(options, list) and options:
            first = options[0]
            if isinstance(first, dict):
                return _sample_json_schema(
                    first,
                    components,
                    depth=depth + 1,
                    max_depth=max_depth,
                    array_items=array_items,
                    object_properties=object_properties,
                )

    schema_type = schema.get("type")
    if schema_type == "array" or "items" in schema:
        items_schema = schema.get("items", {"type": "string"})
        if not isinstance(items_schema, dict):
            items_schema = {"type": "string"}
        return [
            _sample_json_schema(
                items_schema,
                components,
                depth=depth + 1,
                max_depth=max_depth,
                array_items=array_items,
                object_properties=object_properties,
            )
            for _ in range(array_items)
        ]

    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not isinstance(properties, dict) or not properties:
            return {}
        sampled_object: dict[str, Any] = {}
        for index, name in enumerate(_ordered_property_names(properties)):
            if index >= object_properties:
                break
            property_schema = properties.get(name)
            if not isinstance(property_schema, dict):
                continue
            sampled_object[name] = _sample_json_schema(
                property_schema,
                components,
                depth=depth + 1,
                max_depth=max_depth,
                array_items=_array_items_for_property(name, array_items),
                object_properties=object_properties,
            )
        return sampled_object

    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    if schema_type == "integer":
        return schema.get("default", 1)
    if schema_type == "number":
        return schema.get("default", 1.0)
    if schema_type == "boolean":
        return schema.get("default", False)
    if schema_type == "null":
        return None
    return schema.get("default", "string")


def _array_items_for_property(name: str, default: int) -> int:
    if name in {"results", "filters", "lists", "rows", "items"}:
        return min(default, 1)
    return default


def _ordered_property_names(properties: dict[str, Any]) -> list[str]:
    names = list(properties.keys())
    prioritized = [name for name in _PRIORITY_OBJECT_PROPERTIES if name in names]
    remaining = sorted(name for name in names if name not in _PRIORITY_OBJECT_PROPERTIES)
    return prioritized + remaining
