from collections.abc import Sequence

from django.core.paginator import InvalidPage
from rest_framework.response import Response

from management.helpers import DetailedPagination
from management.helpers.detailed_pagination import get_paginated_format_v2

_MISSING = object()


def _get_nested_export_value(source: dict, path: list[str]):
    value = source
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _set_nested_export_value(target: dict, path: list[str], value) -> None:
    cursor = target
    for part in path[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[path[-1]] = value


def ensure_export_fields(data: dict, requested_fields: list[str] | None) -> dict:
    if not requested_fields:
        return data

    for field_name in requested_fields:
        if "." in field_name:
            path = field_name.split(".")
            if _get_nested_export_value(data, path) is _MISSING:
                _set_nested_export_value(data, path, None)
        elif field_name not in data:
            data[field_name] = None
    return data


def build_paginated_export_response(
    request,
    queryset,
    serializer_class,
    *,
    export_columns_only_fields: Sequence[str] | None = None,
    allowed_fields: Sequence[str] | None = None,
    extra_serializer_context: dict | None = None,
) -> Response:
    """
    Shared helper for list export endpoints.

    - `?export_columns_only=true` returns one row with all export keys set to None.
    - No `page_size` param returns the full export (legacy behavior).
    - With `page` + `page_size`, returns a single export page as a plain list.
    """
    selected_fields_raw = request.query_params.get("fields", "")
    selected_fields = [field.strip() for field in selected_fields_raw.split(",") if field.strip()]

    export_columns_only = request.query_params.get("export_columns_only", "").lower() in ("1", "true", "yes")
    if export_columns_only_fields and export_columns_only:
        headers = selected_fields if selected_fields else list(export_columns_only_fields)
        if allowed_fields is not None:
            allowed = set(allowed_fields)
            headers = [field for field in headers if field in allowed]
        return Response([{name: None for name in headers}])

    serializer_context = dict(extra_serializer_context or {})
    if selected_fields:
        serializer_context["selected_fields"] = selected_fields

    page_size_param = request.query_params.get("page_size")
    if page_size_param is None:
        serializer = serializer_class(queryset, many=True, context=serializer_context)
        return Response(serializer.data)

    try:
        page = int(request.query_params.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(page_size_param)
    except (TypeError, ValueError):
        page_size = DetailedPagination.page_size

    page_size = min(max(page_size, 1), DetailedPagination.max_page_size)

    try:
        paginated = get_paginated_format_v2(queryset, page_size, page)
    except InvalidPage:
        return Response([])

    serializer = serializer_class(paginated["results"], many=True, context=serializer_context)
    return Response(serializer.data)
