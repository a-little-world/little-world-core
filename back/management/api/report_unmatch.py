from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from dataclasses import dataclass
from rest_framework_dataclasses.serializers import DataclassSerializer
from rest_framework import serializers
from rest_framework import status
from management import models as management_models
from rest_framework.decorators import api_view, permission_classes


@dataclass
class UnmatchReportParam:
    match_id: str
    reason: str


class UnmatchReportSerializer(DataclassSerializer):
    class Meta:
        dataclass = UnmatchReportParam


def process_report_unmatch(request, kind="report"):
    assert kind in ["report", "unmatch"]

    serializer = UnmatchReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.save()

    matching = management_models.Match.get_matching(request.user, data.match_id)

    if not matching.exists():
        raise serializers.ValidationError("This match does not exist")

    if matching.support_matching:
        raise serializers.ValidationError("You can not report a support match!")

    matching = matching.first()

    matching.active = False
    matching.report_unmatch.append(
        {
            "kind": kind,
            "reason": data.reason,
            "match_id": data.match_id,
            "user_id": request.user.pk,
            "user_uuid": request.user.hash,
        }
    )
    matching.save()

    return Response("Unmatched & Reported!", status=status.HTTP_200_OK)


@extend_schema(
    request=UnmatchReportSerializer(many=False),
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def report(request):
    return process_report_unmatch(request, kind="report")


@extend_schema(
    request=UnmatchReportSerializer(many=False),
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def unmatch(request):
    return process_report_unmatch(request, kind="unmatch")
