from django.shortcuts import render
from tracking import utils
from django.views import View
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils.translation import gettext as _
from tracking.models import Event


class ViewEmail(UserPassesTestMixin, View):
    login_url = '/login'
    redirect_field_name = 'next'

    @utils.track_event(name=_("Email Viewed"), event_type=Event.EventTypeChoices.REQUEST, tags=["frontend"])
    def get(self, request, **kwargs):
        pass
