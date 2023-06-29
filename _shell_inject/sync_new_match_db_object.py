from back.management import controller  # !dont_include
from back.management import random_test_users  # !dont_include
from back.management.models import User, Profile  # !dont_include
from back.management.models import rooms, Match  # !dont_include
from django.utils import timezone
from back.emails import mails  # !dont_include
import json
# !include from management.models import rooms
# !include from management import controller
# !include from management import random_test_users
# !include from management.models import User, Profile, Match
# !include from emails import mails
from datetime import date, timedelta
from django.core.management import call_command

# We just introduced the new model 'Match' this didn't exist before we need to create it for all already existing users and matches

ALL_MATCHES = set()

def get_match_slug(user1, user2):
    pk1 = user1.pk
    pk2 = user2.pk
    if pk1 <= pk2:
        slug = f"{pk1}-{pk2}"
    else:
        slug = f"{pk2}-{pk1}"
        
for user in User.objects.all():
    for match in user.matches.all():
        ALL_MATCHES.add(get_match_slug(user, match))
        
for match in ALL_MATCHES:
    user1 = User.objects.get(pk=int(match.split('-')[0]))
    user2 = User.objects.get(pk=int(match.split('-')[-1]))
    
    if_staff_matching = user1.is_staff or user2.is_staff
    
    match = Match.objects.create(
        user1=user1, 
        user2=user2, 
        support_matching=if_staff_matching
    )
    
    if user1.hash in user2.state.unconfirmed_matches_stack:
        pass
    else:
        match.confirmed_by.add(user2)

    if user2.hash in user1.state.unconfirmed_matches_stack:
        pass
    else:
        match.confirmed_by.add(user1)
        
    match.save()
    
    if match.confirmed_by.count() == 2:
        match.confirmed = True
        match.save()
    
