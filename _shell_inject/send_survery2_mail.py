from back.management import controller  # !dont_include
from back.management import random_test_users  # !dont_include
from back.management.models import User, Profile  # !dont_include
from back.management.models import rooms  # !dont_include
from back.emails import mails  # !dont_include
# !include from management.models import rooms
# !include from management import controller
# !include from management import random_test_users
# !include from management.models import User, Profile
# !include from emails import mails
from datetime import date
from django.core.management import call_command
from django.utils.translation import gettext_lazy as _, pgettext_lazy

def get_params(user):
    return mails.SurveyInvitation2AniqParams(
        first_name=user.profile.first_name,
        link_url="https://s.surveyplanet.com/iuhajmj7",
        unsubscribe_url1="" # filled automatically
    )
    
user_emails = ["benjamin.tim@gmx.de"]
    
#users = [controller.get_user_by_email("benjamin.tim@gmx.de")]
users = [controller.get_user_by_email(email) for email in user_emails]

reports = controller.send_group_mail(
    users=users,
    subject="Studentin bittet um Unterstützung – Umfrage bei Little World",
    mail_name="survey_aniq_2",
    mail_params_func=get_params,
    unsubscribe_group="survery_requests",
    debug=True
)

print(reports)