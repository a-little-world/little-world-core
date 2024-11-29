from django.db import models
from translations import get_translation
from management.validators import model_validate_first_name, model_validate_second_name
from multiselectfield import MultiSelectField


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
