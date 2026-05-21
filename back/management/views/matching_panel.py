import json

from back.utils import CoolerJson
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import path, re_path
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from management.api.matching_panel_user import get_matching_panel_user_data
from management.helpers import IsAdminOrMatchingUser
from management.permissions import ManagementPermission
from management.utils import check_task_status


def _user_can_access_matching_panel(user) -> bool:
    return user.is_authenticated and (user.is_staff or user.has_perm(ManagementPermission.MATCHING_USER))


@method_decorator(login_required, name="dispatch")
class MatchingPanelView(View):
    def get(self, request, menu=None):
        if not _user_can_access_matching_panel(request.user):
            return render(
                request,
                "admin_pannel_v3_frontend.html",
                {"user": json.dumps({}, cls=CoolerJson)},
            )

        return render(
            request,
            "admin_pannel_v3_frontend.html",
            {
                "user": json.dumps(get_matching_panel_user_data(request.user), cls=CoolerJson),
            },
        )


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def request_task_status(request, task_id):
    # TODO in the future tasks, should be user scoped!
    return Response(check_task_status(task_id))


view_urls = [
    path("matching/", MatchingPanelView.as_view(), name="matching_panel"),
    path("matching/tasks/<str:task_id>/status/", request_task_status, name="request_task_status"),
    re_path(r"^matching/(?P<menu>.*)$", MatchingPanelView.as_view(), name="matching_panel"),
]
