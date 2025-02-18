import json

from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render
from django.urls import path, re_path
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from management.helpers import IsAdminOrMatchingUser


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication])
def matching_panel(request, menu=None):
    return render(request, "admin_pannel_v3_frontend.html")


def check_task_status(task_id):
    from celery.result import AsyncResult

    task = AsyncResult(task_id)

    return {
        "state": task.state,
        "info": json.loads(json.dumps(task.info, cls=DjangoJSONEncoder, default=lambda o: str(o))),
    }


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def request_task_status(request, task_id):
    # TODO in the future tasks, should be user scoped!
    return Response(check_task_status(task_id))


view_urls = [
    path("matching/", matching_panel, name="matching_panel"),
    path("matching/tasks/<str:task_id>/status/", request_task_status, name="request_task_status"),
    re_path(r"^matching/(?P<menu>.*)$", matching_panel, name="matching_panel"),
]
