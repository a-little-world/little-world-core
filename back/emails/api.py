from rest_framework.views import APIView
from rest_framework import authentication, permissions
import dataclasses
from copy import deepcopy
from django.conf import settings
from rest_framework.response import Response
from . import mails


class ListEmailTemplates(APIView):

    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        d = []
        for m in mails.templates:
            _m = deepcopy(m)
            delattr(_m, "params")
            setattr(_m, 'view', f'{settings.BASE_URL}/emails/{_m.name}')
            d.append(_m.__dict__)
        return Response(d)
