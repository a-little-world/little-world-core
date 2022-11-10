from django.db import models
from .user import User


class Settings(models.Model):
    """ Stores the language code of the selected frontend language """
    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Key...

    language = models.CharField(max_length=20, default="en")

    # TODO: add a buch of settings for email notification preferences and co
