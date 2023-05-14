from django.db import models
from rest_framework import serializers
from .user import User
from management.models.profile import Profile
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from uuid import uuid4


def seven_days_from_now():
    return timezone.now() + timedelta(days=7)


class UnconfirmedMatch(models.Model):
    """ One object stored for every jet unconfirmed match"""

    hash = models.UUIDField(
        default=uuid4, editable=False, unique=True)

    user1 = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="unconfirmed_match_user1")

    user2 = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="unconfirmed_match_user2")

    # If closed it's not considered anymore
    closed = models.BooleanField(default=False)

    potential_matching_created_at = models.DateTimeField(auto_now_add=True)

    expires_at = models.DateTimeField(default=seven_days_from_now)

    def is_expired(self, close_if_expired=True):
        expired = self.expires_at < timezone.now()
        if close_if_expired and expired:
            self.closed = True
            self.save()

        return expired

    def get_shared_data(self, user):
        """
        Retrives all data from the other user that is allowed to be shared with the current user 
        TODO: we should ensure that this is only shared with the 'volunteer' user not the 'learner' cause the confirmation is up to the learner
        """
        other_user = self.user1 if self.user1 != user else self.user2
        current_time = timezone.now()

        time_difference = self.expires_at - current_time

        return {
            "hash": str(self.hash),
            "user_hash": other_user.hash,
            "first_name": other_user.first_name,
            "image_type": other_user.profile.image_type,
            "avatar_image": other_user.profile.avatar_config if other_user.profile.image_type == Profile.ImageTypeChoice.AVATAR else other_user.profile.image.url,
            "days_until_expiration": str(time_difference.days),
        }


def get_unconfirmed_matches(user):

    # First check if the user is 'volunteer' cause we only allow learners to confirm matches, otherwise return empty list
    if user.profile.user_type == Profile.TypeChoices.VOLUNTEER:
        return []

    unconfirmed = list(UnconfirmedMatch.objects.filter(
        Q(user1=user) | Q(user2=user)).filter(closed=False))

    # Remove expired matches & get the shared data
    unconfirmed = [usr.get_shared_data(user) for usr in unconfirmed if not usr.is_expired(
        close_if_expired=True)]

    return unconfirmed
