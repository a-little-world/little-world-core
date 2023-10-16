from django.db import models
from django.utils.text import slugify
from uuid import uuid4
from .user import User
import time
import random


class CardContent(models.Model):
    """
    Store Categories and their slug
    """
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    content = models.JSONField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    category_name = models.JSONField(null=True, blank=True)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return str(self.category_name)

    def save(self, *args, **kwargs):
        # Generate a slug if one is not provided
        base_slug = slugify(str(self.category_name))

        num = random.randint(1, 100000)

        timestamp = int(time.time() * 1000)  # Multiply by 1000 to get milliseconds

        # Add some additional randomness (you can adjust this part)
        randomness = hash(str(timestamp)) % 1000  # Use a hash function to add some randomness

        # Combine timestamp and randomness to create a unique number
        unique_number = timestamp + randomness + num
        # Append a counter to the base slug until it's unique
        slug = f"{base_slug}-{unique_number}"

        self.slug = slug
        super().save(*args, **kwargs)


class UserDeck(models.Model):
    """
    Store Card content data according to categories
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    categories = models.ManyToManyField(CardContent, related_name='user_decks')

    def __str__(self):
        return str(self.user)
