from back.utils import _api_url
from django.urls import path
from .api import EventTriggerApi

urlpatterns = [
    path(_api_url('track'), EventTriggerApi.as_view()),
]
