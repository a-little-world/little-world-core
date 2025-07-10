from django.urls import path

from .api import EventTriggerApi, SearchEventMetadataApi, SearchEventMetadataPostgressApi

urlpatterns = [
    path("api/track/", EventTriggerApi.as_view()),
    path("api/events/psql_str_search/", SearchEventMetadataPostgressApi.as_view()),
    path("api/events/str_search/", SearchEventMetadataApi.as_view()),
]
