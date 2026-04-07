from uuid import uuid4

from chat.models import Message
from django.db import models
from django.db.models import Count, Max, Q
from django.db.models.functions import Greatest, Least
from django.utils import timezone
from video.models import LivekitSession

from management.models import profile
from management.models import user as user_model
from management.models.unconfirmed_matches import MatchType


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
    first_interaction_at = models.DateTimeField(default=None, null=True, blank=True)
    latest_counter_sync = models.DateTimeField(default=timezone.now)

    interaction_reminder_2_days_send = models.BooleanField(default=False, null=False, blank=False)
    interaction_reminder_7_days_send = models.BooleanField(default=False, null=False, blank=False)
    interaction_reminder_14_days_send = models.BooleanField(default=False, null=False, blank=False)

    auto_email_m031_send = models.BooleanField(default=False, null=False, blank=False)
    auto_email_m032_send = models.BooleanField(default=False, null=False, blank=False)
    auto_email_m033_send = models.BooleanField(default=False, null=False, blank=False)
    auto_email_m042_send = models.BooleanField(default=False, null=False, blank=False)

    # Video Call X conratulation
    auto_email_m043_send = models.BooleanField(default=False, null=False, blank=False)
    auto_email_m044_send = models.BooleanField(default=False, null=False, blank=False)
    auto_email_m045_send = models.BooleanField(default=False, null=False, blank=False)

    completed_5_video_calls = models.BooleanField(default=False, null=False, blank=False)
    completed_8_video_calls = models.BooleanField(default=False, null=False, blank=False)
    completed_10_video_calls = models.BooleanField(default=False, null=False, blank=False)

    # If a certain match completed condition is met, this will be set to True
    completed = models.BooleanField(default=False)
    completed_off_plattform = models.BooleanField(default=False)
    completed_off_plattform_auto_marked_at = models.DateTimeField(default=None, null=True, blank=True)
    auto_marking_updated_logs = models.JSONField(default=list)

    send_automatic_message_1week = models.BooleanField(default=True)

    # 15 days single party contact emails:
    auto_email_fm021_send = models.BooleanField(default=False, null=False, blank=False)
    auto_email_fm022_send = models.BooleanField(default=False, null=False, blank=False)
    is_ghosted_match = models.BooleanField(default=False, null=False, blank=False)
    marked_as_ghosted_at = models.DateTimeField(default=None, null=True, blank=True)
    ghosted_by = models.ForeignKey(
        "management.User", on_delete=models.CASCADE, related_name="ghosted_by", null=True, blank=True
    )

    # YES - case confirm email 'automatic-emails-m051'
    auto_email_m051_send = models.BooleanField(default=False, null=False, blank=False)

    match_type = models.CharField(
        max_length=20,
        choices=MatchType.choices,
        default=MatchType.STANDARD,
    )

    def sync_counters(self):
        sync_match_counters_for_queryset([self])

    @classmethod
    def get_match(cls, user1, user2):
        """Return active matches between two users (all types except TEMPORARY)."""
        return cls.objects.filter(
            Q(user1=user1, user2=user2, active=True) | Q(user1=user2, user2=user1, active=True)
        ).exclude(match_type=MatchType.TEMPORARY)

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
        return (
            cls.objects.filter(Q(user1=user) | Q(user2=user), active=True, confirmed_by=user, support_matching=False)
            .exclude(match_type=MatchType.TEMPORARY)
            .order_by(order_by)
        )

    @classmethod
    def get_unconfirmed_matches(cls, user, order_by="created_at"):
        return (
            cls.objects.filter(
                Q(user1=user) | Q(user2=user), ~Q(confirmed_by=user), active=True, support_matching=False
            )
            .exclude(match_type=MatchType.TEMPORARY)
            .order_by(order_by)
        )

    @classmethod
    def get_support_matches(cls, user, order_by="created_at"):
        return cls.objects.filter(Q(user1=user) | Q(user2=user), active=True, support_matching=True).order_by(order_by)

    @classmethod
    def get_inactive_matches(cls, user, order_by="created_at"):
        return (
            cls.objects.filter(Q(user1=user) | Q(user2=user), active=False, support_matching=False)
            .exclude(match_type=MatchType.TEMPORARY)
            .order_by(order_by)
        )

    @classmethod
    def update_deleted_user_matches(cls, user):
        """
        Get all active matches for a user and set them to inactive.
        This is typically used when deleting a user account.
        """
        active_matches = cls.objects.filter(Q(user1=user) | Q(user2=user), active=True)

        for match in active_matches:
            match.report_unmatch.append(
                {
                    "kind": "user_deleted",
                    "reason": "User account was deleted",
                    "match_id": match.id,
                    "time": str(timezone.now()),
                    "user_id": user.pk,
                    "user_uuid": user.hash,
                }
            )
            match.save()

        return active_matches


def sync_match_counters_for_queryset(matches):
    matches = list(matches)
    if not matches:
        return 0

    now = timezone.now()
    pair_to_matches = {}
    for match in matches:
        pair = tuple(sorted((match.user1_id, match.user2_id)))
        pair_to_matches.setdefault(pair, []).append(match)

    message_pair_filter = Q()
    video_pair_filter = Q()
    for u1_id, u2_id in pair_to_matches:
        message_pair_filter |= Q(sender_id=u1_id, recipient_id=u2_id) | Q(sender_id=u2_id, recipient_id=u1_id)
        video_pair_filter |= Q(u1_id=u1_id, u2_id=u2_id) | Q(u1_id=u2_id, u2_id=u1_id)

    message_stats = {}
    if message_pair_filter:
        grouped_messages = (
            Message.objects.filter(message_pair_filter)
            .annotate(
                pair_user_low=Least("sender_id", "recipient_id"), pair_user_high=Greatest("sender_id", "recipient_id")
            )
            .values("pair_user_low", "pair_user_high")
            .annotate(total_messages=Count("id"), newest_message_at=Max("created"))
        )
        message_stats = {(item["pair_user_low"], item["pair_user_high"]): item for item in grouped_messages}

    video_stats = {}
    if video_pair_filter:
        grouped_video_calls = (
            LivekitSession.objects.filter(video_pair_filter, both_have_been_active=True)
            .annotate(pair_user_low=Least("u1_id", "u2_id"), pair_user_high=Greatest("u1_id", "u2_id"))
            .values("pair_user_low", "pair_user_high")
            .annotate(total_video_calls=Count("id"), newest_video_call_at=Max("created_at"))
        )
        video_stats = {(item["pair_user_low"], item["pair_user_high"]): item for item in grouped_video_calls}

    for match in matches:
        pair = tuple(sorted((match.user1_id, match.user2_id)))

        message_data = message_stats.get(pair, {})
        video_data = video_stats.get(pair, {})

        match.total_messages_counter = message_data.get("total_messages", 0)
        match.total_mutal_video_calls_counter = video_data.get("total_video_calls", 0)

        newest_message_at = message_data.get("newest_message_at")
        newest_video_call_at = video_data.get("newest_video_call_at")
        if newest_message_at and newest_video_call_at:
            match.latest_interaction_at = max(newest_message_at, newest_video_call_at)

        # also we have to check if a match is falsely confirmed=False
        if match.total_messages_counter > 0 or match.total_mutal_video_calls_counter > 0:
            match.confirmed = True

        if match.total_mutal_video_calls_counter >= 5:
            match.completed_5_video_calls = True

        if match.total_mutal_video_calls_counter >= 8:
            match.completed_8_video_calls = True

        if match.total_mutal_video_calls_counter >= 10:
            match.completed_10_video_calls = True

        match.latest_counter_sync = now
        match.updated_at = now

    Match.objects.bulk_update(
        matches,
        [
            "total_messages_counter",
            "total_mutal_video_calls_counter",
            "latest_interaction_at",
            "confirmed",
            "completed_5_video_calls",
            "completed_8_video_calls",
            "completed_10_video_calls",
            "latest_counter_sync",
            "updated_at",
        ],
    )
    return len(matches)
