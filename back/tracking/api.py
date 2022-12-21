from rest_framework.views import APIView
from django.conf import settings
from django.contrib.postgres.search import SearchVector
from django.db.models import TextField
from drf_spectacular.utils import extend_schema
from django.db.models.functions import Cast
from typing import Optional
from rest_framework import status
from rest_framework import authentication, permissions
from dataclasses import dataclass
from rest_framework import serializers
from rest_framework.response import Response
from .utils import inline_track_event
from .models import Event


@dataclass
class EventTriggerGetParams:
    name: Optional[str] = None
    tags: Optional[list] = None
    meta: Optional[dict] = None


class EventTriggerGetSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    tags = serializers.ListField(required=False)
    meta = serializers.JSONField(required=False)

    def create(self, validated_data):
        return EventTriggerGetParams(**validated_data)


class EventTriggerApi(APIView):
    """
    General api to create an event object
    we provide **both** 'post' and 'get'
    for a more complete tracking we should always call POST
    but for cross site or small event tracking it is sufficient to call 'get'
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        serializer = EventTriggerGetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        params = serializer.save()
        _params = params.__dict__
        inline_track_event(
            *[request],
            **{k: _params[k] for k in _params if k},
            event_type=Event.EventTypeChoices.FRONT,
            caller=request.user
        )

        return Response("ok")


@dataclass
class SearchEventMataInputParams:
    search_string: str
    include_meta: bool = False
    start_date: Optional[str] = None
    end_data: Optional[str] = None


class SearchEventMataInputSerializer(serializers.Serializer):
    search_string = serializers.CharField(max_length=150, required=True)
    include_meta = serializers.BooleanField(required=False)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)

    def create(self, validated_data):
        return SearchEventMataInputParams(**validated_data)


class SearchEventMetadataPostgressApi(APIView):

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=SearchEventMataInputSerializer(many=False)
    )
    def post(self, request):
        """
        This is a more efficient filter search meant for usage with Postress DB only 
        If in dev use the sqllite3 compatibe api below
        """
        serializer = SearchEventMataInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        params = serializer.save()

        events = None
        if params.start_date and params.end_data:
            events = Event.objects.annotate(
                search=SearchVector(Cast('metadata', TextField())),
            ).filter(
                time__gte=params.start_date,
                time__lte=params.end_data
            ).filter(search=params.search_string)
        elif params.start_date:
            events = Event.objects.annotate(
                search=SearchVector(Cast('metadata', TextField())),
            ).filter(
                time__gte=params.start_date
            ).filter(search=params.search_string)
        elif params.end_data:
            events = Event.objects.annotate(
                search=SearchVector(Cast('metadata', TextField())),
            ).filter(
                time__lte=params.end_data
            ).filter(search=params.search_string)
        else:
            events = Event.objects.annotate(
                search=SearchVector(Cast('metadata', TextField())),
            ).filter(search=params.search_string)

        filtered_events = []

        for event in events:
            _data = {
                "hash": event.hash,
                "link": f"{settings.BASE_URL}/admin/tracking/event/?q={event.hash}",
            }
            if params.include_meta:
                _data["metadata"] = event.metadata
            filtered_events.append(_data)

        return Response(filtered_events)


class SearchEventMetadataApi(APIView):

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=SearchEventMataInputSerializer(many=False)
    )
    def post(self, request):
        serializer = SearchEventMataInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        params = serializer.save()

        events = None
        if params.start_date and params.end_data:
            events = Event.objects.filter(
                time__gte=params.start_date,
                time__lte=params.end_data
            )
        elif params.start_date:
            events = Event.objects.filter(
                time__gte=params.start_date
            )
        elif params.end_data:
            events = Event.objects.filter(
                time__lte=params.end_data
            )
        else:
            events = Event.objects.all()

        filtered_events = []

        for event in events:
            if params.search_string in str(event.metadata):
                _data = {
                    "hash": event.hash,
                    "link": f"{settings.BASE_URL}/admin/tracking/event/?q={event.hash}",
                }
                if params.include_meta:
                    _data["metadata"] = event.metadata
                filtered_events.append(_data)

        return Response(filtered_events)
