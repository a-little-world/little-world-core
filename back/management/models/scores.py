from django.db import models
from django.db.models import Q
from django.utils import timezone

from management.models.user import User


class TwoUserMatchingScore(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="two_user_matching_score_user1")
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="two_user_matching_score_user2")

    score = models.FloatField(default=0)
    matchable = models.BooleanField(default=False)
    scoring_results = models.JSONField(default=dict)
    latest_update = models.DateTimeField(auto_now=True)

    def __save__(self, *args, **kwargs):
        if self.user1.id > self.user2.id:
            self.user1, self.user2 = self.user2, self.user1

        self.latest_update = timezone.now()
        super().__save__(*args, **kwargs)

    @classmethod
    def get_score(cls, user1, user2):
        if user1.id > user2.id:
            user1, user2 = user2, user1
        score = cls.objects.filter(user1=user1, user2=user2)
        if score.exists():
            return score.first()
        return None

    @classmethod
    def get_or_create(cls, user1, user2):
        if user1.id > user2.id:
            user1, user2 = user2, user1

        score = cls.objects.filter(user1=user1, user2=user2)
        if score.exists():
            return score.first()
        score = cls.objects.create(user1=user1, user2=user2)
        return score

    @classmethod
    def get_matching_scores(cls, user, matchable_only=True):
        if matchable_only:
            return cls.objects.filter(Q(user1=user) | Q(user2=user), matchable=True)
        return cls.objects.filter(Q(user1=user) | Q(user2=user))

    @classmethod
    def delete_if_exists(user1, user2):
        if user1.id > user2.id:
            user1, user2 = user2, user1
        TwoUserMatchingScore.objects.filter(user1=user1, user2=user2).delete()
