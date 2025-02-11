from django.db import models
from rest_framework import serializers

from back.utils import get_options_serializer


class NewsItem(models.Model):
    title = models.CharField(max_length=255, null=False, blank=False)
    description = models.CharField(max_length=255, null=False, blank=False)

    time = models.DateTimeField(null=False, blank=False)

    link = models.CharField(default="", max_length=255)

    active = models.BooleanField(default=False)

    @classmethod
    def get_all_active_news_items(cls):
        return cls.objects.all().filter(active=True)


class NewsItemSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    def get_options(self, obj):
        return get_options_serializer(self, obj)

    class Meta:
        model = NewsItem
        fields = ["title", "description", "time", "options", "link"]
