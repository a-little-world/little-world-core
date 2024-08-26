from django.db import models
from management.models.user import User


class TranslationLog(models.Model):
    time = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    source_lang = models.CharField(max_length=255)
    dest_lang = models.CharField(max_length=255)

    text = models.TextField()

    translation = models.TextField()
