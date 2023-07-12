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

def send_interview_request(email):
    user = controller.get_user_by_email(email)
    settings_hash = user.settings.email_settings.hash
    unsub_link = f"https://little-world.com/api/emails/toggle_sub/?choice=False&unsubscribe_type=interview_requests&settings_hash={settings_hash}"
    mails.send_email(
        recivers=[email],
        subject=pgettext_lazy(
            "api.special-interview-request-subject", "Einladung zum Online-Interview mit Aniqa"),
        mail_data=mails.get_mail_data_by_name("interview"),
        mail_params=mails.InterviewInvitationParams(
            first_name=user.profile.first_name,
            email_aniqa="aniqa.rahman@student.uni-siegen.de",
            link_url="https://calendly.com/d/y3c-7yr-tzq/getting-to-know-interview-for-little-world",
            unsubscribe_url1=unsub_link
        )
)

send_interview_request("benjamin.tim@gmx.de")