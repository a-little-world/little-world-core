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

call_command('makemigrations', interactive=False)
call_command('migrate', interactive=False)
call_command('flush', interactive=False)

# create the base admin user
base_admin = controller.get_base_management_user()

test_users = random_test_users.create_abunch_of_users(10)
for u in test_users:
    us = u.state
    us.email_authenticated = True
    us.save()

u1, u2 = test_users[:2]

random_test_users.modify_profile_to_match(u1, u2)

# then make a matching proposal for these two users
controller.create_user_matching_proposal({u1, u2}, send_confirm_match_email=False)