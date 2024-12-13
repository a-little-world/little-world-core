from django.db import models
from translations import get_translation
from management.validators import model_validate_first_name, model_validate_second_name
from multiselectfield import MultiSelectField
from uuid import uuid4

# TODO: To re-establish the matching process we need to:
# DONE 1. Create the new organizationUserMatching 
# 2. Add an API that allows the user to request matching with a specific organization
# --> Update the api call in the frontend when the api is called on a pre-selected organization
# --> Fix contact form submission inside the components/organization/OrganizationContactModal.js Model :)
# 3. Implement "OrgaEmail: 'we found a candidate for you'"
# 4. Implement "User Email": 'we forwarded your request to the patenmatch organization'
# 5. Implement Email "Did the organization contact you?"
# 6. Implement API to anser 'YES/NO' did the organization contact you?
# TODO: don't expose non critical organization data!

# Missing Emails:
# - confirm_email ( adjust signup email )
# - match result
# - qa orga ( when user responded after 4 weeks that the org didn't contact them)
# - qa request user ( ask the user if he was contacted by the orga )


class SupportGroups(models.TextChoices):
    FAMILY = "family", get_translation("patenmatch.supportgroups.family", lang="de")
    CHILD = "child", get_translation("patenmatch.supportgroups.child", lang="de")
    SENIOR = "senior", get_translation("patenmatch.supportgroups.senior", lang="de")
    INDIVIDUAL = "individual", get_translation("patenmatch.supportgroups.individual", lang="de")
    ADOLESCENT = "adolescent", get_translation("patenmatch.supportgroups.adolescent", lang="de")
    STUDENT = "student", get_translation("patenmatch.supportgroups.student", lang="de")
    ERROR = "error", get_translation("patenmatch.supportgroups.error", lang="de")


class PatenmatchUser(models.Model):
    first_name = models.CharField(max_length=150, blank=False, validators=[model_validate_first_name])
    last_name = models.CharField(max_length=150, blank=False, validators=[model_validate_second_name])
    postal_code = models.CharField(max_length=255, blank=True)
    email = models.EmailField(max_length=50)
    support_for = models.CharField(choices=SupportGroups.choices, max_length=255, blank=False, default=SupportGroups.INDIVIDUAL)
    created_at = models.DateTimeField(auto_now_add=True)
    status_access_token = models.CharField(default=uuid4, max_length=255)
    email_auth_hash = models.CharField(default=uuid4, max_length=255)
    email_authenticated = models.BooleanField(default=False)
    spoken_languages = models.TextField(blank=True)
    request_specific_organization = models.ForeignKey('PatenmatchOrganization', on_delete=models.CASCADE, blank=True, null=True)
    
class PatenmatchOrganizationUserMatching(models.Model):
    organization = models.ForeignKey('PatenmatchOrganization', on_delete=models.CASCADE)
    user = models.ForeignKey('PatenmatchUser', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class PatenmatchOrganization(models.Model):
    name = models.CharField(max_length=1024, blank=False)
    postal_code = models.CharField(max_length=255, blank=False)
    contact_first_name = models.CharField(max_length=150, blank=False, validators=[model_validate_first_name])
    contact_second_name = models.CharField(max_length=150, blank=False, validators=[model_validate_second_name])
    contact_email = models.EmailField(max_length=50, unique=True)
    contact_phone = models.CharField(max_length=255, blank=True)
    maximum_distance = models.IntegerField(blank=True, default=50)
    capacity = models.IntegerField(blank=True, default=3)
    target_groups = MultiSelectField(choices=SupportGroups.choices, max_length=255, blank=True)
    logo_url = models.URLField(max_length=1024, blank=True)
    website_url = models.URLField(max_length=1024, blank=True)
    matched_users = models.ManyToManyField(PatenmatchUser, blank=True)
    metadata = models.JSONField(blank=True, default=dict)
    status_access_token = models.CharField(default=uuid4, max_length=255)
