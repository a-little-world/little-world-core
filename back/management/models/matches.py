from django.db import models
from django.db.models import Q
from back.utils import _double_uuid
from uuid import uuid4
from .user import User



class Match(models.Model):

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    confirmed = models.BooleanField(default=False)
    
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user2')
    
    support_matching = models.BooleanField(default=False)
    
    def get_partner(self, user):
        return self.user1 if self.user2 == user else self.user2
    
    @classmethod
    def get_confirmed_matches(cls, user, order_by='created_at'):
        return cls.objects.filter(Q(user1=user) | Q(user2=user), confirmed=True, support_matching=False).order_by(order_by)

    @classmethod
    def get_unconfirmed_matches(cls, user, order_by='created_at'):
        return cls.objects.filter(Q(user1=user) | Q(user2=user), confirmed=False, support_matching=False).order_by(order_by)
    
    @classmethod
    def get_support_matches(cls, user, order_by='created_at'):
        return cls.objects.filter(Q(user1=user) | Q(user2=user), support_matching=True).order_by(order_by)