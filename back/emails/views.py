from django.shortcuts import render
from tracking import utils
from django.views import View
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils.translation import gettext as _
from tracking.models import Event
from .mails import get_mail_data_by_name


class ViewEmail(UserPassesTestMixin, View):
    login_url = '/login'
    redirect_field_name = 'next'

    def test_func(self):
        return not self.request.user.is_anonymous and self.request.user.is_staff  # type: ignore

    @utils.track_event(
        name=_("Email Viewed"),
        event_type=Event.EventTypeChoices.REQUEST,
        tags=["frontend"], track_arguments=["mail_name"])
    def get(self, request, **kwargs):

        if not 'mail_name' in kwargs:
            raise Exception(_("No mail template with that name"))

        mail_name = kwargs.get('mail_name')
        print("TBS: " + str(mail_name))
        mail_data = get_mail_data_by_name(mail_name)
        return render(request, mail_data.template, {})
