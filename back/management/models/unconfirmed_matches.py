from datetime import timedelta
from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.dispatch import receiver
from django.utils import timezone

from management.models.profile import Profile, ProposalProfileSerializer


class MatchType(models.TextChoices):
    STANDARD = "standard", "Standard Match"
    RANDOM_CALL = "random_call", "Random Call Match"
    TEMPORARY = "temporary", "Temporary Match"


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
                "partner": {
                    "id": str(partner.hash),
                    "has_match_priority": partner.state.has_match_priority,
                    **ProposalProfileSerializer(partner.profile).data,
                },
                "status": "proposed",
                "match_type": proposal.match_type,
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

    # (monitor for bugs!) are there? potential side effect here? if users decide to change their user type after they recieved a matching suggestion!?
    # Maybe we should later save the users here as volunteer / learner and not perform any lookups on the current profile since it could have changed?
    user1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="unconfirmed_match_user1")

    user2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="unconfirmed_match_user2")

    # User who should see and confirm the proposal (STANDARD: the learner; RANDOM_CALL: the non-requester).
    # Stored at creation so it doesn't change if user type changes later.
    confirming_user = models.ForeignKey(
        "management.User",
        on_delete=models.CASCADE,
        related_name="unconfirmed_match_confirming_user",
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

    match_type = models.CharField(
        max_length=20,
        choices=MatchType.choices,
        default=MatchType.STANDARD,
    )

    expired = models.BooleanField(default=False)
    expires_at = models.DateTimeField(default=three_days_from_now, null=True, blank=True)

    expired_mail_send = models.BooleanField(default=False)

    @classmethod
    def get_open_proposals(cls, user, order_by="potential_matching_created_at"):
        proposals = cls.objects.filter(Q(user1=user) | Q(user2=user), closed=False)
        for prop in proposals:
            prop.is_expired(close_if_expired=True, send_mail_if_expired=True)
        return (
            cls.objects.filter(Q(user1=user) | Q(user2=user), closed=False)
            .exclude(match_type=MatchType.TEMPORARY)
            .order_by(order_by)
        )

    @classmethod
    def get_unsuccessful_proposals(cls, user, order_by="potential_matching_created_at"):
        return (
            cls.objects.filter(
                (Q(user1=user) | Q(user2=user)),
                (Q(expired=True) | Q(rejected=True)),
                closed=True,
            )
            .exclude(match_type=MatchType.TEMPORARY)
            .order_by(order_by)
        )

    @classmethod
    def get_open_proposals_learner(cls, user, order_by="potential_matching_created_at"):
        """Open proposals where this user is the one who should confirm."""
        proposals = cls.objects.filter(
            Q(user1=user, confirming_user=user) | Q(user2=user, confirming_user=user), closed=False
        )
        for prop in proposals:
            prop.is_expired(close_if_expired=True, send_mail_if_expired=True)
        return cls.objects.filter(
            Q(user1=user, confirming_user=user) | Q(user2=user, confirming_user=user), closed=False
        ).order_by(order_by)

    @classmethod
    def close_open_proposals_for_deleted_user(cls, user):
        """Close all open proposed matches for a user being deleted."""
        cls.objects.filter(
            Q(user1=user) | Q(user2=user),
            closed=False,
        ).update(
            closed=True,
            expired=True,
            expired_mail_send=True,
        )

    @classmethod
    def get_proposal_between(cls, user1, user2):
        return cls.objects.filter(Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1))

    def is_expired(self, close_if_expired=True, send_mail_if_expired=False):
        if self.match_type == MatchType.RANDOM_CALL or self.expires_at is None:
            return False
        expired = self.expires_at < timezone.now()
        if close_if_expired and expired:
            self.closed = True
            self.expired = True
            self.save()

            if send_mail_if_expired:
                self.send_expiration_mail()

        return expired

    def get_confirming_user(self):
        """User who should confirm the proposal (receives proposal emails etc.)."""
        return self.confirming_user

    def get_learner(self):
        """Alias for get_confirming_user (the user who confirms is the learner for STANDARD proposals)."""
        return self.get_confirming_user()

    def send_initial_mail(self):
        """Send the new-match proposal email for STANDARD proposals only."""
        if self.match_type != MatchType.STANDARD:
            return
        if self.send_inital_mail:
            return
        confirming_user = self.get_confirming_user()
        if confirming_user is None:
            return
        self.send_inital_mail = True
        self.save(update_fields=["send_inital_mail"])
        confirming_user.send_email("confirm-match-1", proposed_match_id=self.id)

    def send_expiration_mail(self):
        if self.expired_mail_send:
            return
        confirming_user = self.get_confirming_user()
        if confirming_user is None:
            return
        self.expired_mail_send = True
        self.save(update_fields=["expired_mail_send"])
        from management.tasks import send_email_background

        send_email_background.delay("automatic-emails-fm001", user_id=confirming_user.id)

    def get_partner(self, user):
        return self.user1 if self.user2 == user else self.user2

    def is_reminder_due(self, send_reminder=True):
        reminder_due = self.reminder_due_at < timezone.now()
        if send_reminder and reminder_due and (not self.reminder_send):
            confirming_user = self.get_confirming_user()
            if confirming_user is not None:
                self.reminder_send = True
                self.save(update_fields=["reminder_send"])
                confirming_user.send_email("confirm-match-2", proposed_match_id=self.id)
        return reminder_due

    def get_shared_data(self, user):
        """
        Retrives all data from the other user that is allowed to be shared with the current user
        """
        other_user = self.user1 if self.user1 != user else self.user2
        days_until_expiration = None
        if self.expires_at is not None:
            current_time = timezone.now()
            time_difference = self.expires_at - current_time
            days_until_expiration = str(time_difference.days)

        return {
            "hash": str(self.hash),
            "user_hash": other_user.hash,
            "first_name": other_user.first_name,
            "image_type": other_user.profile.image_type,
            "avatar_image": other_user.profile.avatar_config
            if other_user.profile.image_type == Profile.ImageTypeChoice.AVATAR
            else other_user.profile.image.url,
            "days_until_expiration": days_until_expiration,
        }

    def save(self, *args, **kwargs):
        """
        On first save (insert), set confirming_user when not already set:
        - STANDARD: set to the learner (derived from user1/user2 profile).
        - RANDOM_CALL: must be provided by the caller at creation (cannot be derived from model fields).
        Both match types are handled in the same way: confirming_user is set before the insert completes.
        """
        if self._state.adding and self.confirming_user_id is None:
            if self.match_type == MatchType.STANDARD:
                self.confirming_user = (
                    self.user1 if self.user1.profile.user_type == Profile.TypeChoices.LEARNER else self.user2
                )
            # RANDOM_CALL: confirming_user is set by the caller (e.g. create_user_matching_proposal(..., confirming_user=...))
        if self._state.adding and self.match_type == MatchType.RANDOM_CALL:
            self.expires_at = None
        super(ProposedMatch, self).save(*args, **kwargs)


# Send the new-match proposal email when a new proposal is created (for both STANDARD and RANDOM_CALL).
@receiver(models.signals.post_save, sender=ProposedMatch)
def execute_after_save(sender, instance, created, *args, **kwargs):
    if created:
        instance.send_initial_mail()


def get_unconfirmed_matches(user):
    # Proposals where this user is the one who should confirm (confirming_user=user).
    # STANDARD: only learners see them (volunteers do not confirm standard proposals).
    # RANDOM_CALL: the person who didn't request sees the proposal (confirming_user set to non-requester).
    qs = ProposedMatch.objects.filter(
        Q(user1=user, confirming_user=user) | Q(user2=user, confirming_user=user),
        closed=False,
    )
    if user.profile.user_type == Profile.TypeChoices.VOLUNTEER:
        qs = qs.filter(match_type=MatchType.RANDOM_CALL)
    else:
        qs = qs.filter(match_type__in=(MatchType.STANDARD, MatchType.RANDOM_CALL))

    unconfirmed = list(qs)

    # Remove expired matches & get the shared data
    unconfirmed = [usr.get_shared_data(user) for usr in unconfirmed if not usr.is_expired(close_if_expired=True)]

    return unconfirmed
