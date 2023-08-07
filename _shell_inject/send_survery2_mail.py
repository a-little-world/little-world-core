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
    return mails.SurveryInvitation3Natalia(
        first_name=user.profile.first_name,
        unsubscribe_url1="" # filled automatically
    )
    
user_emails = ["benjamin.tim@gmx.de"]

#users = [controller.get_user_by_email("benjamin.tim@gmx.de")]
users = [controller.get_user_by_email(email) for email in user_emails]

reports = controller.send_group_mail(
    users=users,
    subject="Einladung zu einem Online-Interview mit Natalia",
    mail_name="survey3_natalia",
    mail_params_func=get_params,
    unsubscribe_group="survery_requests",
    debug=True
)

print(reports)