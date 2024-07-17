
from django.db import models

class Statistic(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    name = models.CharField(max_length=255)
    
    data = models.JSONField()

    class StatisticTypes(models.TextChoices):
        USER_BUCKET_IDS = 'USER_BUCKET_IDS'
        MATCH_BUCKET_IDS = 'MATCH_BUCKET_IDS'
    
    kind = models.CharField(max_length=255, choices=StatisticTypes.choices, default=StatisticTypes.USER_BUCKET_IDS)
