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
    return mails.GeneralSurveryMailParams(
        first_name=user.profile.first_name,
        link_url="https://forms.gle/cokJiymoBkpDHA1Z6",
        unsubscribe_url1="" # filled automatically
    )
    
users = [controller.get_user_by_email("benjamin.tim@gmx.de")]

controller.send_group_mail(
    users=users,
    subject="Unterstütze uns mit nur 3 Minuten deiner Zeit!",
    mail_name="general_interview",
    mail_params_func=get_params,
    unsubscribe_group="survery_requests"
)