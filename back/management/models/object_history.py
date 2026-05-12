from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class ObjectHistory(models.Model):
    class Type(models.TextChoices):
        CREATE = "CREATE", _("Create")
        UPDATE = "UPDATE", _("Update")
        DELETE = "DELETE", _("Delete")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    changed_by = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=10, choices=Type.choices)
    field = models.CharField(max_length=100, null=True, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["changed_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]


def log_history(obj, *, type: ObjectHistory.Type, changed_by=None, field=None, old_value=None, new_value=None) -> None:
    ObjectHistory.objects.create(
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        changed_by=changed_by,
        type=type,
        field=field,
        old_value=old_value,
        new_value=new_value,
    )


class ObjectHistorySerializer(serializers.ModelSerializer):
    model_type = serializers.SerializerMethodField()

    def get_model_type(self, obj) -> str:
        return obj.content_type.model

    class Meta:
        model = ObjectHistory
        fields = ["id", "model_type", "changed_by_id", "changed_at", "type", "field", "old_value", "new_value"]
