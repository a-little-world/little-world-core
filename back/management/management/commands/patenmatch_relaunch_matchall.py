import csv
import json
from patenmatch.models import PatenmatchUser, PatenmatchOrganizationUserMatching
from patenmatch.matching import find_organization_match
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, **options):
        
        all_pt_users = PatenmatchUser.objects.all()
        
        matched_users = []
        unmatchable_users = []
        matches = []
        
        c = 0
        for pt_user in all_pt_users:
            c += 1
            print(f"Processing user ({c}/{all_pt_users.count()})")
            
            match = find_organization_match(pt_user)

            if match is None:
                print("No match found")
                unmatchable_users.append(pt_user)
                continue
            
            print("Match found")

            context = {
                "organization_name": match.name,
                "patenmatch_first_name": pt_user.first_name,
                "patenmatch_last_name": pt_user.last_name,
                "patenmatch_email": pt_user.email,
                "patenmatch_target_group_name": pt_user.support_for,
                "patenmatch_postal_address": pt_user.postal_code,
                "patenmatch_language": pt_user.spoken_languages or "Not set"
            }
            
            matched_users.append(pt_user)
            matches.append(context)
            
            # TODO: create the models
            # TODO: all to 'org.matched_users'
            # TODO: send email to user
            
        print(f"Of {all_pt_users.count()} users, {len(matched_users)} are able to be matched and {len(unmatchable_users)} are not matchable.")

