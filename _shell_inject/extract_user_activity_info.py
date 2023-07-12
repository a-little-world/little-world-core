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

state_file = "active_users_map.json"

amount_users = User.objects.all().count()

i = 0

active_users_map = {}

current_time = timezone.now()
withing_4_weeks = current_time - timedelta(days=80)

for user in User.objects.all():
    print(f"Scanning users: ({i}/{amount_users})")
    with open(state_file, "r") as fp:
        active_users_map = json.load(fp)
        
    if user.email == "littleworld.management@gmail.com":
        i += 1
        continue
    
    if user.last_login and (user.last_login < withing_4_weeks):
        print("User not active")
        i += 1
        continue
    
    if user.hash in active_users_map:
        i += 1
        continue

    activity_info = controller.extract_user_activity_info(user)
    
    if activity_info["email_verified"] and \
        (activity_info["current_matches"] > 1) and \
            (activity_info["form_finished"]) and \
                (activity_info["messages_send_total"] > 10):

        active_users_map[user.hash] = activity_info
            
    with open(state_file, "w") as fp:
        json.dump(active_users_map, fp, indent=2, default=str)
        
    i += 1
    
print("AMOUNT of users ", len(list(active_users_map.keys())))
    
# sort the users by degree of activity