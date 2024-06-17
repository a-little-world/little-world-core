from rest_framework import viewsets, authentication, permissions
import io
import re
from management.models.profile import SelfProfileSerializer, Profile
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework.views import APIView
from rest_framework import serializers, status
from dataclasses import dataclass
from back.utils import transform_add_options_serializer
from management.models.help_message import HelpMessage
from django.core.validators import MaxLengthValidator, MinLengthValidator


def validate_message_characters(value):
    corrected_value = re.sub(r"[^a-zA-Z0-9\s,.:!?\-]", "_", value)
    return corrected_value


class SendHelpMessageSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        validators=[MinLengthValidator(3), MaxLengthValidator(2000)],
    )
    file = serializers.ListField(child=serializers.FileField(), required=False)

    def validate_message(self, value):
        return validate_message_characters(value)

    def create(self, validated_data):
        return validated_data


class SendHelpMessage(APIView):
    authentication_classes = [
        authentication.SessionAuthentication,
        authentication.BasicAuthentication,
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
                    raise serializers.ValidationError(
                        {"file": "Maximum 3 files allowed"}
                    )

        HelpMessage.objects.create(
            user=request.user,
            message=data["message"],
            **patt,
        )

        return Response("Successfully submitted help message!")
