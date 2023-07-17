from back.management import controller  # !dont_include
from back.management import random_test_users  # !dont_include
from back.management.models import User, Profile  # !dont_include
from back.management.models import rooms  # !dont_include
from django.utils import timezone
from back.emails import mails  # !dont_include
import json
# !include from management.models import rooms
# !include from management import controller
# !include from management import random_test_users
# !include from management.models import User, Profile
# !include from emails import mails
from datetime import date, timedelta
from django.core.management import call_command

user = controller.get_user_by_email("albakermohamad17@gmail.com")
controller.extract_user_activity_info(user)

### mission: find our most active volunteers
querryset = User.objects.all().filter(profile__user_type="volunteer")

state_file = "active_users_map.json"

amount_users = querryset.count()

i = 0

active_users_map = {}

current_time = timezone.now()
LOGIN_WITHIN_DAYS = 220

MIN_TOTAL_MSG = 5

collected = 0

for user in querryset:
    print(f"Scanning users: ({i}/{amount_users})")
    with open(state_file, "r") as fp:
        active_users_map = json.load(fp)
        
    if user.email == "littleworld.management@gmail.com":
        i += 1
        continue
    

    if user.last_login:
        login_delta = (current_time - user.last_login)
        
        if not (login_delta.days < LOGIN_WITHIN_DAYS):
            i += 1
            print("Login to long ago", user.email, str(user.last_login), current_time, login_delta.days, login_delta)
            continue
    
    
    if user.hash in active_users_map:
        i += 1
        continue

    activity_info = controller.extract_user_activity_info(user)
    
    if activity_info["email_verified"] and activity_info["form_finished"] and (activity_info["current_matches"] >= 2) and (activity_info["messages_send_total"] >= MIN_TOTAL_MSG):

        activity_info["last_login"] = str(user.last_login)
        active_users_map[user.hash] = activity_info
        collected += 1
    else:
        print("NOT adding to inactive", user.email, activity_info)
            
    with open(state_file, "w") as fp:
        json.dump(active_users_map, fp, indent=2, default=str)
        
    i += 1
    
print("AMOUNT of users ", len(list(active_users_map.keys())))
    
# sort the users by degree of activity