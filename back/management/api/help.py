from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.utils.html import escape
from drf_spectacular.utils import extend_schema
from rest_framework import authentication, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from management.authentication import NativeOnlyJWTAuthentication
from management.models.help_message import HelpMessage
from management.models.user import User
from management.tasks import slack_notify_communication_channel_async


class SendHelpMessageSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        validators=[MinLengthValidator(3), MaxLengthValidator(2000)],
    )
    file = serializers.ListField(child=serializers.FileField(), required=False)
    kind = serializers.CharField(required=False, allow_blank=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    reported_user_id = serializers.CharField(required=False, allow_null=True)
    origin = serializers.CharField(required=False, allow_blank=True)

    def validate_message(self, value):
        return escape(value)

    def create(self, validated_data):
        return validated_data


class SendHelpMessage(APIView):
    authentication_classes = [
        authentication.SessionAuthentication,
        NativeOnlyJWTAuthentication,
    ]

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=SendHelpMessageSerializer(many=False),
    )
    def post(self, request):
        # print("TBS", request.data, request.FILES)
        s = SendHelpMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.save()

        patt = {}
        if "file" in data:
            c = 1
            for f in data["file"]:
                patt["attachment" + str(c)] = f.read()
                c += 1
                if c > 3:
                    raise serializers.ValidationError({"file": "Maximum 3 files allowed"})

        # Handle reported_user if provided
        reported_user = None
        if data.get("reported_user_id"):
            try:
                reported_user = User.objects.get(hash=data["reported_user_id"])
            except User.DoesNotExist as exc:
                raise serializers.ValidationError({"reported_user_id": "Reported user does not exist"}) from exc

        # Validate kind if provided, default to "general" if not provided
        kind = data.get("kind")
        if not kind:
            kind = HelpMessage.KindChoices.GENERAL

        if kind not in [choice[0] for choice in HelpMessage.KindChoices.choices]:
            raise serializers.ValidationError(
                {"kind": f"Kind must be one of: {', '.join([choice[0] for choice in HelpMessage.KindChoices.choices])}"}
            )

        # If kind is report_user or report_partner, reported_user_id is required
        if kind in [HelpMessage.KindChoices.REPORT_USER, HelpMessage.KindChoices.REPORT_PARTNER] and not reported_user:
            raise serializers.ValidationError(
                {"reported_user_id": f"reported_user_id is required when kind is '{kind}'"}
            )

        help_message = HelpMessage.objects.create(
            user=request.user,
            message=data["message"],
            kind=kind,
            keywords=data.get("keywords", []),
            reported_user=reported_user,
            origin=data.get("origin"),
            **patt,
        )

        # Create Slack message
        slack_message = f"Help Message ({kind}) by {request.user.username} with message: {data['message']}\n\nCheck as super user at https://little-world.com/admin/management/helpmessage/{help_message.id}/change/"

        slack_notify_communication_channel_async.delay(slack_message)

        return Response(
            {"id": help_message.id, "message": "Issue reported successfully"}, status=status.HTTP_201_CREATED
        )
