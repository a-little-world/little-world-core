from django.contrib.auth.mixins import LoginRequiredMixin
from back.utils import CoolerJson
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
import json
from dataclasses import dataclass, field
from django.shortcuts import render, redirect
from django.urls import reverse
from rest_framework.request import Request
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework import serializers
from django.views import View
from rest_framework.response import Response
from typing import List, Optional
from tracking import utils
from tracking.models import Event
from rest_framework.decorators import api_view, permission_classes
from management.views.main_frontend import info_card

@api_view(['GET'])
@permission_classes([])
def landing_page(request):
    
    return info_card(request,
            title=settings.LANDINGPAGE_PLACEHOLDER_TITLE,
            content="here could be a landing page",
            linkText="Go to the app",
            linkTo="/login")
