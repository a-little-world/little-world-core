from django.db import models
from .user import User
import json
import base64
import zlib
import random
from datetime import datetime
from django.utils.translation import pgettext_lazy, gettext_lazy as _
from rest_framework import serializers
from .notifications import Notification
from back.utils import get_options_serializer
from back import utils
from multiselectfield import MultiSelectField


class MangementTask(models.Model):
    """
    A simple container for a task model to be used by the management admin users 
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='state_created_by', null=True, blank=True)
    
    class MangementTaskStates(models.TextChoices):
        OPEN = 'OPEN', _('Open')
        IN_PROGRESS = 'IN_PROGRESS', _('In progress')
        FINISHED = 'FINISHED', _('Finished')
        
    state = models.CharField(
        max_length=20,
        choices=MangementTaskStates.choices,
        default=MangementTaskStates.OPEN,
    )
    
    description = models.TextField(null=True, blank=True)
    
    @classmethod
    def create_task(cls, user, description, management_user=None):
        """
        Create a new task for the user
        """
        if not management_user:
            from management.controller import get_base_management_user
            management_user = get_base_management_user()
        task = cls.objects.create(
            created_by=management_user,
            user=user, 
            description=description
        )
        Notification.create_notification(user, 'New task', 'You have a new task assigned to you')
        return task