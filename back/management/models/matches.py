from django.db import models
from django.db.models import Q
from back.utils import _double_uuid
from uuid import uuid4
from .user import User



class Match(models.Model):

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # If a match is active, if it's not its basicly not a match anymore
    active = models.BooleanField(default=True)
    
    confirmed = models.BooleanField(default=False)
    
    confirmed_by = models.ManyToManyField(User, related_name='users_confirmed_match')
    
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='match_user1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='match_user2')
    
    support_matching = models.BooleanField(default=False)
    
    @classmethod
    def get_match(cls, user1, user2):
        return cls.objects.filter(Q(user1=user1) | Q(user2=user2))
    
    def get_partner(self, user):
        return self.user1 if self.user2 == user else self.user2
    
    def confirm(self, user):
        if(self.user1 in self.confirmed_by.all() and self.user2 in self.confirmed_by.all()):
            self.confirmed = True
        if(user not in self.confirmed_by.all()):
            self.confirmed_by.add(user)
        self.save()
    
    @classmethod
    def get_confirmed_matches(cls, user, order_by='created_at'):
        return cls.objects.filter(
            Q(user1=user) | Q(user2=user), 
            active=True,
            confirmed_by=user, 
            support_matching=False
            ).order_by(order_by)

    @classmethod
    def get_unconfirmed_matches(cls, user, order_by='created_at'):
        return cls.objects.filter(
            Q(user1=user) | Q(user2=user), 
            ~Q(confirmed_by=user), 
            active=True, 
            support_matching=False).order_by(order_by)
    
    @classmethod
    def get_support_matches(cls, user, order_by='created_at'):
        return cls.objects.filter(
            Q(user1=user) | Q(user2=user), 
            active=True, 
            support_matching=True
            ).order_by(order_by)