from django.db import models
from django.utils.text import slugify
from uuid import uuid4
from .user import User
import time
import base64
import random
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_unique(value):
    cleaned_string = slugify(value)
    hashed_string = base64.b64encode(cleaned_string.encode()).decode()
    if hashed_string in CardContent.objects.all().values_list("slug", flat=True):
        raise ValidationError(
            _("%(value)s is already present"),
            params={"value": value},
        )

def validate_unique_content(value):
    
    if value in CardContent.objects.all().values_list("content", flat=True):
        raise ValidationError(
            _("This Question is already present"),
            params={"value": value},
        )

class CardContent(models.Model):
    """
    Store Categories and their slug
    """
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, validators=[validate_unique_content])
    content = models.JSONField(null=True, blank=True, unique=True)
    is_archived = models.BooleanField(default=False)
    category_name = models.JSONField(null=True, blank=True)
    slug = models.SlugField(unique=True, validators=[validate_unique])

    def __str__(self):
        return str(self.category_name)

    def save(self, *args, **kwargs):
        if not self.slug:
            values_list = list(self.content.values())
            result_string = ' '.join(values_list)
            cleaned_string = slugify(result_string)
            hashed_string = base64.b64encode(cleaned_string.encode()).decode()
            self.slug = hashed_string
        else:
            cleaned_string = slugify(self.slug)
            hashed_string = base64.b64encode(cleaned_string.encode()).decode()
            self.slug = hashed_string
        super(CardContent, self).save(*args, **kwargs)
    
class UserDeck(models.Model):
    """
    Store Card content data according to User
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    content_id = models.ManyToManyField(CardContent, related_name='user_decks')

    def __str__(self):
        return str(self.user)