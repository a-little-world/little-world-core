import urllib.parse
from dataclasses import dataclass

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import authentication, permissions, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_dataclasses.serializers import DataclassSerializer

from back.utils import transform_add_options_serializer
from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS
from management.api.options import get_options_dict
from management.models.banner import Banner, BannerSerializer
from management.models.community_events import CommunityEvent, CommunityEventSerializer
from management.models.matches import Match
from management.models.notifications import Notification, SelfNotificationSerializer
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from management.models.profile import CensoredProfileSerializer, ProposalProfileSerializer, SelfProfileSerializer
from management.models.state import FrontendStatusSerializer, State
from management.models.unconfirmed_matches import ProposedMatch
from management.helpers.detailed_pagination import get_paginated_format_v2

def serialize_community_events(events):
    serialized = []

    for event in events:
        serialized.append(CommunityEventSerializer(event).data)

    return serialized


def serialize_notifications(notifications):
    serialized = []

    for notification in notifications:
        serialized.append(SelfNotificationSerializer(notification).data)

    return serialized