from back import utils
from django.db import models
from rest_framework import serializers
from .user import User


class HelpMessage(models.Model):
    """
    Stores help messages send by users 
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    hash = models.CharField(max_length=100, blank=True,
                            unique=True, default=utils._double_uuid)  # type: ignore

    attachment1 = models.BinaryField(blank=True, null=True)
    attachment2 = models.BinaryField(blank=True, null=True)
    attachment3 = models.BinaryField(blank=True, null=True)

    message = models.TextField()
