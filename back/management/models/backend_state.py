from django.db import models
from back.utils import _double_uuid


class BackendState(models.Model):
    """
    This is a stateclass for managing backend states 
    e.g.: This stores if certain events happened yet
    in order of assuring event dont restart even if some memory state is reset
    ---> default event's created, adin user created
    NOTE this should only be used on rare startup events not on events that can occur often!
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class BackendStateEnum(models.TextChoices):
        default_community_events = "db-created-default-cummunity-events"
        default_cookies = "db-created-default-cookies-and-cookiegroups"
        base_management_user_profile = "db-filled-base-management-user-profile"
        default_score_source_created = "db-created-default-score-source"
        pre_matching_call_active = "pre-matching-call-active"

    slug = models.CharField(null=False, blank=False,
                            choices=BackendStateEnum.choices, unique=True, max_length=255)

    name = models.CharField(default="master", unique=True, max_length=255)
    hash = models.CharField(default=_double_uuid, max_length=255)
    meta = models.JSONField(default=dict)

    @classmethod
    def exists_or_create(cls, enum_slug, set_true=True):
        exists = cls.objects.filter(
            slug=enum_slug).exists()
        if exists:
            return True
        else:
            if set_true:
                cls.objects.create(
                    slug=enum_slug,
                    name="automatic event " + str(_double_uuid()),
                )
            return False

    @classmethod
    def are_default_cookies_set(cls, set_true=False):
        return cls.exists_or_create(
            cls.BackendStateEnum.default_cookies, set_true=set_true)

    @classmethod
    def are_default_community_events_set(cls, set_true=False):
        return cls.exists_or_create(
            cls.BackendStateEnum.default_community_events, set_true=set_true)

    @classmethod
    def is_base_management_user_profile_filled(cls, set_true=False):
        return cls.exists_or_create(
            cls.BackendStateEnum.base_management_user_profile, set_true=set_true)

    @classmethod
    def is_default_score_source_created(cls, set_true=False):
        return cls.exists_or_create(
            cls.BackendStateEnum.default_score_source_created, set_true=set_true)
        
    @classmethod
    def get_prematch_callinvitations_state(cls):
        backend_state = cls.objects.filter(slug=cls.BackendStateEnum.pre_matching_call_active)
        if backend_state.exists():
            return backend_state
        else:
            backend_state = cls.objects.create(
                slug=cls.BackendStateEnum.pre_matching_call_active,
                name="Pre Match Video Calls",
                meta={
                    "active": False,
                    "invitations_remaining": 10
                }
            )
            return backend_state
