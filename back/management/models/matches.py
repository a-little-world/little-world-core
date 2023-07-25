from django.db import models
from django.db.models import Q
from back.utils import _double_uuid
from management import models as management_models
from uuid import uuid4



class Match(models.Model):
    
    ## TODO: ensure no dumplicate entries can exist!

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # If a match is active, if it's not its basicly not a match anymore
    active = models.BooleanField(default=True)
    
    confirmed = models.BooleanField(default=False)
    
    confirmed_by = models.ManyToManyField("management.User", related_name='users_confirmed_match')
    
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    
    user1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name='match_user1')
    user2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name='match_user2')
    
    support_matching = models.BooleanField(default=False)
    
    report_unmatch = models.JSONField(default=list)
    
    @classmethod
    def get_match(cls, user1, user2):
        return cls.objects.filter(Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1))
    
    @classmethod
    def get_matches(cls, user, order_by='created_at'):
        user1_partners_ids = cls.objects.filter(user1=user, active=True).values_list('user2', flat=True)
        user2_partners_ids = cls.objects.filter(user2=user, active=True).values_list('user1', flat=True)
        user_partners_ids = user1_partners_ids.union(user2_partners_ids)

        partners = management_models.User.objects.filter(id__in=user_partners_ids).exclude(id=user.pk)
        return partners
    
    @classmethod
    def get_matching(cls, user, matching_uuid):
        return cls.objects.filter(
            Q(user1=user) | Q(user2=user), 
            active=True, 
            uuid=matching_uuid, 
        )
    
    @classmethod
    def get_match_by_hash(cls, user, matching_uuid):
        return cls.objects.filter(
            Q(user1=user) | Q(user2=user), 
            active=True, 
            uuid=matching_uuid
            ).first()
        
    def get_serialized(self, user):
        partner = self.get_partner(user)
        return {
            "user": management_models.CensoredUserSerializer(partner).data,
            "profile": management_models.CensoredProfileSerializer(partner.profile).data,
        }

    
    def get_partner(self, user):
        return self.user1 if (self.user2 == user) else self.user2
    
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