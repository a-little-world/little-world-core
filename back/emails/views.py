from django.shortcuts import render
from tracking import utils
from django.views import View
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils.translation import gettext_lazy as _
from tracking.models import Event
from management.models.state import State
from emails.mails import get_mail_data_by_name, decode_mail_params
from emails.templates import inject_template_data


class ViewEmail(UserPassesTestMixin, View):
    login_url = '/login'
    redirect_field_name = 'next'

    def test_func(self):
        if self.request.user.is_anonymous:
            return False
        if self.request.user.is_staff:
            return True
        if self.request.user.is_authenticated and \
             self.request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.EMAIL_TEMPLATES_VIEW):
            return True
        if self.request.user.is_authenticated and \
            self.request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            # TODO: re-evaluate if matching users should be allowed here?
            return True
        return False

    def get(self, request, **kwargs):

        if not 'mail_name' in kwargs:
            raise Exception(_("No Template Name provided!"))

        mail_name = kwargs.get('mail_name')
        mail_data = get_mail_data_by_name(mail_name)

        parms = None
        if 'mail_params' in kwargs:
            # Means someone is requesting to render an email
            # TODO: wrap try!
            parms = decode_mail_params(kwargs["mail_params"])
            print("PBS: decoded" + str(parms))
        if not parms:
            context_dict = {k: getattr(mail_data.defaults, k)
                            for k in mail_data.defaults.__annotations__}
            #print("TBS dict", mail_data.defaults.__dict__)
            return render(request, mail_data.template, context_dict)
        else:
            # In this case we dont show the default template data
            context_dict = {k: getattr(mail_data.texts, k)
                            for k in mail_data.texts.__annotations__}
            _data = inject_template_data(context_dict, parms)
            return render(request, mail_data.template, _data)
