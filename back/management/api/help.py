from rest_framework import viewsets, authentication, permissions
import io
from ..models import SelfProfileSerializer, Profile
from django.utils.translation import pgettext_lazy
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework.views import APIView
from rest_framework import serializers, status
from dataclasses import dataclass
from back.utils import transform_add_options_serializer


class SendHelpMessageSerializer(serializers.Serializer):
    message = serializers.CharField(required=True)
    file = serializers.ListField(child=serializers.FileField(), required=False)

    def create(self, validated_data):
        return validated_data


class SendHelpMessage(APIView):

    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        #print("TBS", request.data, request.FILES)
        s = SendHelpMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.save()
        from ..models.help_message import HelpMessage

        patt = {}
        if 'file' in data:
            c = 1
            for f in data["file"]:
                patt["attachment" +
                     str(c)] = f.read()
                c += 1
                if c > 3:
                    raise serializers.ValidationError(
                        {"file": "Maximum 3 files allowed"})

        HelpMessage.objects.create(
            user=request.user,
            message=data["message"],
            **patt,
        )

        return Response("Successfully submitted help message!")
