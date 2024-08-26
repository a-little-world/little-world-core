from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from typing import OrderedDict


class DetailedPagination(PageNumberPagination):
    page_size = 10
    max_page_size = 100
    page_query_param = "page"
    page_size_query_param = "page_size"

    def get_page_size(self, request):
        if self.page_size_query_param:
            page_size = request.query_params.get(self.page_size_query_param)
            if page_size is not None:
                page_size = int(page_size)
                if page_size > self.max_page_size:
                    page_size = self.max_page_size
                return page_size
        return self.page_size

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "page_size": {"type": "integer", "example": "40", "description": "The number of items per page", "format": "int32"},
                "pages_total": {"type": "integer", "example": "1", "description": "The total number of pages", "format": "int32"},
                "items_total": {"type": "integer", "example": "1", "description": "The total number of items", "format": "int32"},
                "next_page": {"type": "integer", "example": "2", "description": "The next page number", "format": "int32"},
                "previous_page": {"type": "integer", "example": "1", "description": "The previous page number", "format": "int32"},
                "first_page": {"type": "integer", "example": "1", "description": "The first page number", "format": "int32"},
                "last_page": {"type": "integer", "example": "1", "description": "The last page number", "format": "int32"},
                "next": {
                    "type": "string",
                    "example": "http://example.com/api/organizations/?page=2",
                    "description": "The URL to the next page",
                },
                "previous": {
                    "type": "string",
                    "example": "http://example.com/api/organizations/?page=1",
                    "description": "The URL to the previous page",
                },
                "results": schema,
            },
        }

    def get_paginated_response(self, data):
        ## TODO: this is overly verbose at the moment as we are migrating from two slighly different fronten pagination shemas
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("page", self.page.number),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),  # The  following are extras added by me:
                    ("page_size", self.get_page_size(self.request)),
                    ("next_page", self.page.next_page_number() if self.page.has_next() else None),
                    ("previous_page", self.page.previous_page_number() if self.page.has_previous() else None),
                    ("last_page", self.page.paginator.num_pages),
                    ("items_total", self.page.paginator.count),
                    ("first_page", 1),
                ]
            )
        )


class DetailedPaginationMixin(DetailedPagination):
    pass
