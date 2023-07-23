from back.management import controller  # !dont_include
from back.management import random_test_users  # !dont_include
from back.management.models import User, Profile  # !dont_include
from back.management.models import rooms  # !dont_include
from back.emails.models import EmailLog # !dont_include
from django.utils import timezone
from back.emails import mails  # !dont_include
import json
# !include from management.models import rooms
# !include from management import controller
# !include from management import random_test_users
# !include from management.models import User, Profile
# !include from emails import mails
# !include from emails.models import EmailLog
from datetime import date, timedelta
from django.core.management import call_command


emails_interview2 = EmailLog.objects.filter(template="survey_aniq_2")

email_list = []

for log in emails_interview2:
    print(log.receiver.email)
    print("----")
    
    email_list.append(log.receiver.email)
    
with open("emails_interview2.json", "w+") as fp:
    json.dump(email_list, fp)
    
print("Total emails:", len(email_list))