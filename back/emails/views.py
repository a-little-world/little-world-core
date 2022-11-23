from django.shortcuts import render
from tracking import utils
from django.views import View
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils.translation import gettext_lazy as _
from tracking.models import Event
from .mails import get_mail_data_by_name, decode_mail_params


class ViewEmail(UserPassesTestMixin, View):
    login_url = '/login'
    redirect_field_name = 'next'

    # TODO: if there are params passed /emails/<template>/params
    # then also regular users should be allowed
    def test_func(self):
        return not self.request.user.is_anonymous and self.request.user.is_staff  # type: ignore

    @utils.track_event(
        name="Email Viewed",
        event_type=Event.EventTypeChoices.REQUEST,
        tags=["frontend"], track_arguments=["mail_name"])
    def get(self, request, **kwargs):

        if not 'mail_name' in kwargs:
            raise Exception(_("No Template Name provided!"))

        mail_name = kwargs.get('mail_name')
        mail_data = get_mail_data_by_name(mail_name)

        if 'mail_params' in kwargs:
            # Means someone is requesting to render an email
            try:  # try to process the mail params
                parms = decode_mail_params(kwargs["mail_paarams"])
            except:
                raise Exception(_("Params can't be parsed"))
        return render(request, mail_data.template, {})
