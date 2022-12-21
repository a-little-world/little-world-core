from back.utils import _api_url
from django.urls import path
from .api import EventTriggerApi, SearchEventMetadataPostgressApi, SearchEventMetadataApi

urlpatterns = [
    path(_api_url('track'), EventTriggerApi.as_view()),
    path(_api_url('events/psql_str_search'),
         SearchEventMetadataPostgressApi.as_view()),
    path(_api_url('events/str_search'),
         SearchEventMetadataApi.as_view()),
]
