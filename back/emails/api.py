from rest_framework.views import APIView
from dataclasses import dataclass
from rest_framework import authentication, permissions, viewsets, status
from drf_spectacular.utils import extend_schema
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from copy import deepcopy
from rest_framework import serializers
from rest_framework.response import Response
from . import mails
from .models import EmailLog, EmailLogSerializer


class ListEmailTemplates(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        d = []
        for m in mails.templates:
            _m = deepcopy(m)
            prms = {k: repr(v) for k, v in _m.params.__annotations__.items()}
            delattr(_m, "params")
            delattr(_m, "texts")
            delattr(_m, "defaults")
            setattr(_m, "params", prms)
            setattr(_m, "view", f"{settings.BASE_URL}/emails/{_m.name}")
            d.append(_m.__dict__)
        return Response(d)


@dataclass
class EncodeEmailApiParams:
    params: dict
    template: str


class EncodeEmailApiSerializer(serializers.Serializer):
    params = serializers.JSONField(required=True)
    template = serializers.CharField(required=True)

    def create(self, validated_data):
        return EncodeEmailApiParams(**validated_data)


class EncodeTemplate(APIView):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=EncodeEmailApiSerializer(many=False),
    )
    def post(self, request):
        """
        Allowes to encode arbitrary email data in a online renderable email!
        TODO: we want to use this later to render emails in multiple languages

        Currently you can send a json with 'params', 'template' e.g.:
        POST /api/admin/email/template/encode
        {
            "params": {
                "first_name": "Tim",
                "verification_code": "231231",
                "verification_url": "https://t1m.me/"
            },
            "template": "welcome"
        }
        --> "http://localhost:8000/emails/welcome/eJyrVkrLLCouic9LzE1VslJQCsnMVdJRUCpLLcpMy0xOLMnMz4tPzk8ByxkZGwIRhnRpUQ5INqOkpKDYSl-_xDBXLzdVX6kWAFpAHXM="
        At that link you can render the email now !
        """
        serializer = EncodeEmailApiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        template = None
        try:
            template = mails.get_mail_data_by_name(params.template)
        except mails.MailDataNotFoundErr:
            return Response(_("Can't find email template '{name}'".format(name=params.template)), status=status.HTTP_400_BAD_REQUEST)
        assert template, "Template retrival failed with undefined error"
        for param in template.params.__annotations__:
            if param not in params.params:
                return Response(_("Missing param '{name}'".format(name=param)), status=status.HTTP_400_BAD_REQUEST)
        # If we get here all required email params are contained
        encoded = mails.encode_mail_params(params.params)
        as_url = f"{settings.BASE_URL}/emails/{params.template}/{encoded}"
        return Response(as_url)


class EmailListView(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]

    permission_classes = [permissions.IsAdminUser]
    queryset = EmailLog.objects.all()
    serializer_class = EmailLogSerializer
