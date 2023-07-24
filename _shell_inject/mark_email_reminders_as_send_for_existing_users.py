from back.management import controller  # !dont_include
from back.management import random_test_users  # !dont_include
from back.management.models import User, Profile, Settings, EmailSettings  # !dont_include
from back.management.models import rooms, Match  # !dont_include
from django.utils import timezone
from back.emails import mails  # !dont_include
from back.emails.models import EmailLog  # !dont_include
import json
# !include from management.models import rooms
# !include from management import controller
# !include from management import random_test_users
# !include from management.models import User, Profile, Match, Settings, EmailSettings
# !include from emails import mails
# !include from emails.models import EmailLog
from datetime import date, timedelta
from django.core.management import call_command

# We just introduced the new model 'Match' this didn't exist before we need to create it for all already existing users and matches

settings = EmailSettings.objects.all()

count = settings.count()
i = 0 

for setting in settings:
    i+=1
    print(f"Setting {i}/{count}")
    setting.email_verification_reminder1 = True
    setting.user_form_unfinished_reminder1 = True
    setting.user_form_unfinished_reminder2 = True
    setting.save()
    
EmailLog.objects.filter(template="unfinished_user_form_1").delete()
EmailLog.objects.filter(template="unfinished_user_form_2").delete()
EmailLog.objects.filter(template="email_unverified").delete()