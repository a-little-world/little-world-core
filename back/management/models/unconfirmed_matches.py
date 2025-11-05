from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.dispatch import receiver
from django.utils import timezone
from management.models.profile import Profile, ProposalProfileSerializer


def seven_days_from_now():
    return timezone.now() + timedelta(days=7)


def three_days_from_now():
    return timezone.now() + timedelta(days=3)

def one_day_from_now():
    return timezone.now() + timedelta(days=1)

def serialize_proposed_matches(matching_proposals, user):
    serialized = []
    for proposal in matching_proposals:
        partner = proposal.get_partner(user)
        rejected_by = None
        if proposal.rejected_by is not None:
            rejected_by = proposal.rejected_by.hash
        serialized.append(
            {
                "id": str(proposal.hash),
                "partner": {"id": str(partner.hash), **ProposalProfileSerializer(partner.profile).data},
                "status": "proposed",
                "closed": proposal.closed,
                "rejected_by": rejected_by,
                "rejected_at": proposal.rejected_at,
                "rejected": proposal.rejected,
                "expired": proposal.expired,
                "expires_at": proposal.expires_at,
            }
        )

    return serialized


class ProposedMatch(models.Model):
    """One object stored for every jet unconfirmed match"""

    hash = models.UUIDField(default=uuid4, editable=False, unique=True)

    # TODO: there are potential side effect here if users decide to change their user type after they recieved a matching suggestion!
    # Maybe we should later save the users here as volunteer / learner and not perform any lookups on the current profile since it could have changed?
    user1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="unconfirmed_match_user1")

    user2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="unconfirmed_match_user2")

    # This field is a patch fix for the issue if a user decided to changes their user type when this unconfirmed_match was created
    # This way we don't check the current user_type based on the profile,
    # but just teat that user by the user_type he had when this model was created
    learner_when_created = models.ForeignKey(
        "management.User",
        on_delete=models.CASCADE,
        related_name="unconfirmed_match_learner_when_created",
        null=True,
        blank=True,
    )

    # If closed it's not considered anymore when scanning for expired matches
    closed = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    rejected_at = models.DateTimeField(blank=True, null=True)
    rejected_by = models.ForeignKey("management.User", on_delete=models.CASCADE, blank=True, null=True)
    rejected_reason = models.TextField(blank=True, null=True)

    send_inital_mail = models.BooleanField(default=False)

    reminder_send = models.BooleanField(default=False)
    reminder_due_at = models.DateTimeField(default=one_day_from_now)

    potential_matching_created_at = models.DateTimeField(auto_now_add=True)

    expired = models.BooleanField(default=False)
    expires_at = models.DateTimeField(default=three_days_from_now)

    expired_mail_send = models.BooleanField(default=False)

    @classmethod
    def get_open_proposals(cls, user, order_by="potential_matching_created_at"):
        proposals = cls.objects.filter(Q(user1=user) | Q(user2=user), closed=False)
        for prop in proposals:
            prop.is_expired(close_if_expired=True, send_mail_if_expired=True)
        return cls.objects.filter(Q(user1=user) | Q(user2=user), closed=False).order_by(order_by)

    @classmethod
    def get_unsuccessful_proposals(cls, user, order_by="potential_matching_created_at"):
        return cls.objects.filter(
            (Q(user1=user) | Q(user2=user)),
            (Q(expired=True) | Q(rejected=True)),
            closed=True,
        ).order_by(order_by)

    @classmethod
    def get_open_proposals_learner(cls, user, order_by="potential_matching_created_at"):
        proposals = cls.objects.filter(
            Q(user1=user, learner_when_created=user) | Q(user2=user, learner_when_created=user), closed=False
        )
        for prop in proposals:
            prop.is_expired(close_if_expired=True, send_mail_if_expired=True)
        return cls.objects.filter(
            Q(user1=user, learner_when_created=user) | Q(user2=user, learner_when_created=user), closed=False
        ).order_by(order_by)

    @classmethod
    def get_proposal_between(cls, user1, user2):
        return cls.objects.filter(Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1))

    def is_expired(self, close_if_expired=True, send_mail_if_expired=False):
        expired = self.expires_at < timezone.now()
        if close_if_expired and expired:
            self.closed = True
            self.expired = True
            self.save()

            if send_mail_if_expired:
                self.send_expiration_mail()

        return expired

    def get_learner(self):
        return self.learner_when_created

    def send_initial_mail(self):
        if self.send_inital_mail:
            print("Initial mail, already sent")
            return
        from management import controller

        self.send_inital_mail = True
        self.save()

        learner = self.get_learner()
        learner.send_email_v2("confirm-match-1", proposed_match_id=self.id)

    def send_expiration_mail(self):
        # TODO: there are very rare concurrency issues possible here right?
        # If this triggers ending a mail twice in a row very quick, could this be sending two mails then?
        if self.expired_mail_send:
            print("Expiration mail, already sent")
            return

        from management import controller

        self.expired_mail_send = True
        self.save()

        learner = self.get_learner()
        learner.send_email_v2("expired-match", proposed_match_id=self.id)

    def get_partner(self, user):
        return self.user1 if self.user2 == user else self.user2

    def is_reminder_due(self, send_reminder=True):
        reminder_due = self.reminder_due_at < timezone.now()
        if send_reminder and reminder_due and (not self.reminder_send):
            self.reminder_send = True
            self.save()

            from management import controller

            learner = self.get_learner()
            # send groupmail function automaticly checks if users have unsubscribed!
            # we still mark email verification reminder 1 as True, since we at least tried to send it,
            # never wanna send twice! Not even **try** twice!
            other = self.get_partner(learner)
            learner.send_email_v2("confirm-match-2", proposed_match_id=self.id)

        return reminder_due

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
            "avatar_image": other_user.profile.avatar_config
            if other_user.profile.image_type == Profile.ImageTypeChoice.AVATAR
            else other_user.profile.image.url,
            "days_until_expiration": str(time_difference.days),
        }

    def save(self, *args, **kwargs):
        if self._state.adding is True:
            self.learner_when_created = (
                self.user1 if self.user1.profile.user_type == Profile.TypeChoices.LEARNER else self.user2
            )
        super(ProposedMatch, self).save(*args, **kwargs)


# We automaticly send the new-match proposal mail when a new proposal is created
@receiver(models.signals.post_save, sender=ProposedMatch)
def execute_after_save(sender, instance, created, *args, **kwargs):
    if created:
        # Send the new match proposal email
        instance.send_initial_mail()


def get_unconfirmed_matches(user):
    # First check if the user is 'volunteer' cause we only allow learners to confirm matches, otherwise return empty list
    if user.profile.user_type == Profile.TypeChoices.VOLUNTEER:
        return []

    unconfirmed = list(
        ProposedMatch.objects.filter(
            Q(user1=user, learner_when_created=user) | Q(user2=user, learner_when_created=user)
        ).filter(closed=False)
    )

    # Remove expired matches & get the shared data
    unconfirmed = [usr.get_shared_data(user) for usr in unconfirmed if not usr.is_expired(close_if_expired=True)]

    return unconfirmed
