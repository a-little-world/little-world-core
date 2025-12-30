from dataclasses import dataclass
from typing import List, Optional

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer

from management.models.issue_report import IssueReport
from management.models.user import User
from management.tasks import slack_notify_communication_channel_async


@dataclass
class ReportIssueParam:
    kind: str
    keywords: List[str]
    reason: str
    reported_user_id: Optional[int] = None


class ReportIssueSerializer(DataclassSerializer):
    class Meta:
        dataclass = ReportIssueParam


@extend_schema(
    request=ReportIssueSerializer(many=False),
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def report(request):
    """
    Create a new reported issue
    """
    serializer = ReportIssueSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.save()

    # If kind is "user", reported_user_id is required and must be valid
    reported_user = None
    if data.kind == "user":
        if data.reported_user_id is None:
            raise serializers.ValidationError("reported_user_id is required when kind is 'user'")
        try:
            reported_user = User.objects.get(pk=data.reported_user_id)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError("Reported user does not exist") from exc
    elif data.reported_user_id is not None:
        # If kind is not "user" but reported_user_id is provided, still validate it
        try:
            reported_user = User.objects.get(pk=data.reported_user_id)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError("Reported user does not exist") from exc

    reported_issue = IssueReport.objects.create(
        reporting_user=request.user,
        reported_user=reported_user,
        kind=data.kind,
        keywords=data.keywords,
        reason=data.reason,
    )

    # Send Slack notification
    slack_message = f"Issue reported: {data.kind} by {request.user.hash} with reason: {data.reason}"
    slack_notify_communication_channel_async.delay(slack_message)

    return Response({"id": reported_issue.id, "message": "Issue reported successfully"}, status=status.HTTP_201_CREATED)

