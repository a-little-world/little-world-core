import datetime
from back.management import controller  # !dont_include
from back.management.models import User  # !dont_include
from back.management.models import rooms  # !dont_include
from back.emails import mails  # !dont_include
# !include from management.models import rooms
# !include from management import controller
# !include from management.models import User
# !include from emails import mails

today = datetime.datetime.now()
tree_weeks = datetime.timedelta(days=7*3)
tree_weeks_ago = today - tree_weeks

all_users_past_3weeks_loggedin = User.objects.filter(
    last_login__gte=tree_weeks_ago
)


def send_new_server_mail(receiver):
    mails.send_email(
        recivers=[receiver],
        subject="Little World – Serverumzug & Neuigkeiten",
        mail_data=mails.get_mail_data_by_name("new_server"),
        mail_params=mails.NewServerMailParams()
    )


for u in all_users_past_3weeks_loggedin:
    print(u.email)
    print("SENDING ==>", u.email)
    # send_new_server_mail(u.email)
