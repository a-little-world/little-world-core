from uuid import uuid4

from chat.models import Message
from django.db import models
from django.db.models import Q
from django.utils import timezone
from video.models import LivekitSession

from management.models import profile
from management.models import user as user_model



class Match(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # If a match is active, if it's not its basicly not a match anymore
    active = models.BooleanField(default=True)

    confirmed = models.BooleanField(default=False)

    confirmed_by = models.ManyToManyField("management.User", related_name="users_confirmed_match")

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

    user1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="match_user1")
    user2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="match_user2")

    notes = models.TextField(blank=True, null=True)

    support_matching = models.BooleanField(default=False)

    report_unmatch = models.JSONField(default=list)

    still_in_contact_mail_send = models.BooleanField(default=False)

    total_messages_counter = models.IntegerField(default=0)
    total_mutal_video_calls_counter = models.IntegerField(default=0)
    latest_interaction_at = models.DateTimeField(default=timezone.now)

    # If a certain match completed condition is met, this will be set to True
    completed = models.BooleanField(default=False)
    completed_off_plattform = models.BooleanField(default=False)

    send_automatic_message_1week = models.BooleanField(default=True)

    def sync_counters(self):
        self.total_messages_counter = Message.objects.filter(
            Q(sender=self.user1, recipient=self.user2) | Q(sender=self.user2, recipient=self.user1)
        ).count()
        self.total_mutal_video_calls_counter = LivekitSession.objects.filter(
            Q(u1=self.user1, u2=self.user2) | Q(u1=self.user2, u2=self.user1), both_have_been_active=True
        ).count()

        newest_message = (
            Message.objects.filter(
                Q(sender=self.user1, recipient=self.user2) | Q(sender=self.user2, recipient=self.user1)
            )
            .order_by("-created")
            .first()
        )
        newest_video_call = (
            LivekitSession.objects.filter(
                Q(u1=self.user1, u2=self.user2) | Q(u1=self.user2, u2=self.user1), both_have_been_active=True
            )
            .order_by("-created_at")
            .first()
        )

        if newest_message and newest_video_call:
            self.latest_interaction_at = max(newest_message.created, newest_video_call.created_at)

        # also we have to check if a match is falsely confirmed=False
        if self.total_messages_counter > 0 or self.total_mutal_video_calls_counter > 0:
            self.confirmed = True

        # check if the match should permanently be marked as completed!
        from management.api.match_journey_filters import completed_match

        if completed_match(Match.objects.filter(id=self.id)).exists():
            self.completed = True

        self.save()

    @classmethod
    def get_match(cls, user1, user2):
        return cls.objects.filter(Q(user1=user1, user2=user2, active=True) | Q(user1=user2, user2=user1, active=True))

    @classmethod
    def get_matches(cls, user, order_by="created_at"):
        user1_partners_ids = cls.objects.filter(user1=user, active=True).values_list("user2", flat=True)
        user2_partners_ids = cls.objects.filter(user2=user, active=True).values_list("user1", flat=True)
        user_partners_ids = user1_partners_ids.union(user2_partners_ids)

        partners = user_model.User.objects.filter(id__in=user_partners_ids).exclude(id=user.pk)
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
        return cls.objects.filter(Q(user1=user) | Q(user2=user), active=True, uuid=matching_uuid).first()

    def get_serialized(self, user):
        partner = self.get_partner(user)
        return {
            "user": user_model.CensoredUserSerializer(partner).data,
            "profile": profile.CensoredProfileSerializer(partner.profile).data,
        }

    def get_partner(self, user):
        return self.user1 if (self.user2 == user) else self.user2

    def get_learner(self):
        return self.user1 if self.user1.profile.user_type == profile.Profile.TypeChoices.LEARNER else self.user2
    
    def get_volunteer(self):
        return self.user1 if self.user1.profile.user_type == profile.Profile.TypeChoices.VOLUNTEER else self.user2

    def confirm(self, user):
        if user not in self.confirmed_by.all():
            self.confirmed_by.add(user)
        if (self.user1 in self.confirmed_by.all()) and (self.user2 in self.confirmed_by.all()):
            self.confirmed = True
        self.save()

    @classmethod
    def get_confirmed_matches(cls, user, order_by="created_at"):
        return cls.objects.filter(
            Q(user1=user) | Q(user2=user), active=True, confirmed_by=user, support_matching=False
        ).order_by(order_by)

    @classmethod
    def get_unconfirmed_matches(cls, user, order_by="created_at"):
        return cls.objects.filter(
            Q(user1=user) | Q(user2=user), ~Q(confirmed_by=user), active=True, support_matching=False
        ).order_by(order_by)

    @classmethod
    def get_support_matches(cls, user, order_by="created_at"):
        return cls.objects.filter(Q(user1=user) | Q(user2=user), active=True, support_matching=True).order_by(order_by)

    @classmethod
    def get_inactive_matches(cls, user, order_by="created_at"):
        return cls.objects.filter(Q(user1=user) | Q(user2=user), active=False, support_matching=False).order_by(
            order_by
        )

    @classmethod
    def update_deleted_user_matches(cls, user):
        """
        Get all active matches for a user and set them to inactive.
        This is typically used when deleting a user account.
        """
        active_matches = cls.objects.filter(
            Q(user1=user) | Q(user2=user), 
            active=True
        )
        
        for match in active_matches:
            match.report_unmatch.append({
                "kind": "user_deleted",
                "reason": "User account was deleted",
                "match_id": match.id,
                "time": str(timezone.now()),
                "user_id": user.pk,
                "user_uuid": user.hash,
            })
            match.save()
        
        return active_matches
