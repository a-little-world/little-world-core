from rest_framework.decorators import api_view, permission_classes
from django.urls import path, re_path
from rest_framework.permissions import BasePermission
from management.models.state import State
from rest_framework.pagination import PageNumberPagination
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.response import Response
from django.shortcuts import render
from typing import OrderedDict
import json

class IsAdminOrMatchingUser(BasePermission):
    """
    Allows access only to admin users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff) or \
            bool(request.user and request.user.is_authenticated and request.user.state.has_extra_user_permission(
                State.ExtraUserPermissionChoices.MATCHING_USER))
            
class AugmentedPagination(PageNumberPagination):
    page_size = 10
    max_page_size = 100
    page_query_param = 'page'
    page_size_query_param = 'page_size'
    
    def get_page_size(self, request):
        if self.page_size_query_param:
            page_size = request.query_params.get(self.page_size_query_param)
            if page_size is not None:
                page_size = int(page_size)
                if page_size > self.max_page_size:
                    page_size = self.max_page_size
                return page_size
        return self.page_size

    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('page' , self.page.number),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data), # The  following are extras added by me:
            ('page_size', self.get_page_size(self.request)),
            ('next_page', self.page.next_page_number() if self.page.has_next() else None),
            ('previous_page', self.page.previous_page_number() if self.page.has_previous() else None),
            ('last_page', self.page.paginator.num_pages),
            ('first_page', 1),
        ]))

class DetailedPaginationMixin(AugmentedPagination):
    pass

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def matching_panel(request, menu=None):
    return render(request, "admin_pannel_v3_frontend.html")

def check_task_status(task_id):
    from celery.result import AsyncResult
    task = AsyncResult(task_id)
    
    return {
        "state": task.state,
        "info": json.loads(json.dumps(task.info, cls=DjangoJSONEncoder, default=lambda o: str(o))),
    }

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def request_task_status(request, task_id):
    # TODO in the future tasks, should be user scoped!
    return Response(check_task_status(task_id))

view_urls = [
    path(f"matching/", matching_panel, name="matching_panel"),
    path('matching/tasks/<str:task_id>/status', request_task_status, name="request_task_status"),
    re_path(fr'^matching/(?P<menu>.*)$', matching_panel, name="matching_panel"),
]