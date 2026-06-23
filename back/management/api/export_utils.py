from typing import Sequence

from django.core.paginator import InvalidPage
from rest_framework.response import Response

from management.helpers import DetailedPagination
from management.helpers.detailed_pagination import get_paginated_format_v2


def build_paginated_export_response(
    request,
    queryset,
    serializer_class,
    *,
    export_columns_only_fields: Sequence[str] | None = None,
) -> Response:
    """
    Shared helper for list export endpoints.

    - `?export_columns_only=true` returns one row with all export keys set to None.
    - No `page_size` param returns the full export (legacy behavior).
    - With `page` + `page_size`, returns a single export page as a plain list.
    """
    export_columns_only = request.query_params.get("export_columns_only", "").lower() in ("1", "true", "yes")
    if export_columns_only_fields and export_columns_only:
        return Response([{name: None for name in export_columns_only_fields}])

    page_size_param = request.query_params.get("page_size")
    if page_size_param is None:
        serializer = serializer_class(queryset, many=True)
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

    serializer = serializer_class(paginated["results"], many=True)
    return Response(serializer.data)
