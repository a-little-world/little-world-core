from django.urls import path

from back.utils import _api_url

from .api import EventTriggerApi, SearchEventMetadataApi, SearchEventMetadataPostgressApi

urlpatterns = [
    path(_api_url("track"), EventTriggerApi.as_view()),
    path(_api_url("events/psql_str_search"), SearchEventMetadataPostgressApi.as_view()),
    path(_api_url("events/str_search"), SearchEventMetadataApi.as_view()),
]
