from rest_framework.views import APIView
from typing import Optional
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
