from dataclasses import dataclass

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from translations import get_translation

from management import models as management_models
from management.tasks import slack_notify_communication_channel_async, slack_notify_security_channel_async


@dataclass
class UnmatchReportParam:
    match_id: str
    reason: str


class UnmatchReportSerializer(DataclassSerializer):
    class Meta:
        dataclass = UnmatchReportParam


def process_request(request, kind="report"):
    assert kind in ["report", "unmatch", "user_deleted"]

    serializer = UnmatchReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.save()

    matching = management_models.matches.Match.get_matching(request.user, data.match_id)

    if not matching.exists():
        raise serializers.ValidationError("This match does not exist")

    matching = matching.first()

    if matching and matching.support_matching:
        raise serializers.ValidationError("You can not report a support match!")
    assert matching, "Match does not exist!"

    return process_report_unmatch(request.user, matching, kind, data.reason, send_message=True)


def process_report_unmatch(
    user, matching: management_models.matches.Match, kind: str, reason: str, send_message: bool = True
):
    assert kind in ["report", "unmatch", "user_deleted", "ghosted"]

    match_id = str(matching.uuid)
    matching.active = False
    matching.report_unmatch.append(
        {
            "kind": kind,
            "reason": reason,
            "match_id": match_id,
            "user_id": user.pk,
            "user_uuid": str(user.uuid),
            "time": str(timezone.now()),
        }
    )
    matching.save()

    user_name_match = (
        matching.user2.profile.first_name
        if matching.user2.profile.first_name != user.profile.first_name
        else matching.user1.profile.first_name
    )

    if kind == "unmatch":
        default_message = get_translation("auto_messages.match_unmatched", lang="de").format(
            first_name=user.profile.first_name, match_name=user_name_match
        )
    else:
        default_message = get_translation("auto_messages.match_reported", lang="de").format(
            first_name=user.profile.first_name, match_name=user_name_match
        )

    if send_message:
        user.message(default_message)

    slack_message = f"Match {match_id} has been {kind}-ed by {user.uuid} with reason: {reason}"
    if kind == "ghosted":
        slack_message = f"*Automatic Match Removal* - {slack_message}"
        slack_notify_security_channel_async.delay(slack_message)
        slack_notify_communication_channel_async.delay(slack_message)
    else:
        slack_notify_communication_channel_async.delay(slack_message)

    return Response("Unmatched & Reported!", status=status.HTTP_200_OK)


@extend_schema(
    request=UnmatchReportSerializer(many=False),
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def report(request):
    return process_request(request, kind="report")


@extend_schema(
    request=UnmatchReportSerializer(many=False),
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def unmatch(request):
    return process_request(request, kind="unmatch")
