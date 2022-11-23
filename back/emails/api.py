from rest_framework.views import APIView
from rest_framework import authentication, permissions, viewsets
from drf_spectacular.utils import extend_schema, OpenApiParameter
import dataclasses
from copy import deepcopy
from django.conf import settings
from rest_framework.response import Response
from . import mails
from .models import EmailLog, EmailLogSerializer


class ListEmailTemplates(APIView):

    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        d = []
        for m in mails.templates:
            _m = deepcopy(m)
            prms = {k: repr(v) for k, v in _m.params.__annotations__.items()}
            delattr(_m, "params")
            setattr(_m, 'params', prms)
            setattr(_m, 'view', f'{settings.BASE_URL}/emails/{_m.name}')
            d.append(_m.__dict__)
        return Response(d)


class EncodeTemplate(APIView):
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='params', description="",
                             required=False, type=dict)
        ]
    )
    def post(self, request):
        """
        Allowes to encode arbitrary email data in a online renderable email!
        TODO: we want to use this later to render emails in multiple languages
        """
        request.data.get('params')
        pass


class EmailListView(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAdminUser]
    queryset = EmailLog.objects.all()
    serializer_class = EmailLogSerializer
