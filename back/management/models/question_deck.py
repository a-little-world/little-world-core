from typing import Any
from django.db import models
from django.utils.text import slugify
from uuid import uuid4
import time
import base64
import random
from django.core.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.dispatch import receiver


def _base_translations_dict(
        en="",
        de=""
):
    return {
        "de": de,
        "en": en
    }
    

class QuestionCardCategories(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ref_id = models.IntegerField(unique=True, editable=False, default=0)
    content = models.JSONField(default=_base_translations_dict)
    
class QuestionCardsCategoriesSerializer(ModelSerializer):
    class Meta:
        model = QuestionCardCategories
        fields = '__all__'

class QuestionCard(models.Model):
    
    category = models.ForeignKey(QuestionCardCategories, on_delete=models.CASCADE)
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    ref_id = models.IntegerField(unique=True, editable=False, default=0)
    content = models.JSONField(default=_base_translations_dict)
    
class QuestionCardSerializer(ModelSerializer):
    class Meta:
        model = QuestionCard
        fields = '__all__'
        
def _default_cards():
    return QuestionCard.objects.all()

class QuestionCardsDeck(models.Model):
    
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey("management.User", on_delete=models.CASCADE)
    cards = models.ManyToManyField(QuestionCard, related_name='cards')
    cards_archived = models.ManyToManyField(QuestionCard, related_name='cards_archived', blank=True)

    def archive_card(self, card):
        self.cards.remove(card)
        self.cards_archived.add(card)
        self.save()
        
    def unarchive_card(self, card):
        self.cards.add(card)
        self.cards_archived.remove(card)
        self.save()
    

@receiver(post_save, sender=QuestionCardsDeck)
def populate_question_cards(sender, instance, created, **kwargs):
    if created:
        instance.cards.set(QuestionCard.objects.all())
        instance.save()