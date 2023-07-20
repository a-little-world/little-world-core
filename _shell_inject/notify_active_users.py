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


### mission: find our most active volunteers

state_file = "active_users_map.json"
with open(state_file, "r") as fp:
    active_users_map = json.load(fp)
    
print("AMOUNT of users ", len(list(active_users_map.keys())))

users = []
for hash in active_users_map:
    user = controller.get_user_by_hash(hash)
    users.append(user)