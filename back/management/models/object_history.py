from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class ObjectHistory(models.Model):
    class Type(models.TextChoices):
        CREATE = "CREATE", _("Create")
        UPDATE = "UPDATE", _("Update")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    changed_by = models.ForeignKey(
        "management.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",  # Disable reverse relation
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=10, choices=Type.choices)
    field = models.CharField(max_length=100, null=True, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    value_model = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        ordering = ["changed_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]


def log_history(
    obj, *, type: ObjectHistory.Type, changed_by=None, field=None, old_value=None, new_value=None, value_model=None
) -> None:
    ObjectHistory.objects.create(
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        changed_by=changed_by,
        type=type,
        field=field,
        old_value=old_value,
        new_value=new_value,
        value_model=value_model,
    )


_RESOLVABLE_MODELS: frozenset[str] = frozenset(["management.User"])


def _serialize_resolved(model_label: str, instance) -> dict | None:
    if model_label == "management.User":
        from management.models.support_task import _serialize_user_profile

        return _serialize_user_profile(instance)
    raise ValueError(f"No serializer registered for {model_label}")


class ObjectHistorySerializer(serializers.ModelSerializer):
    model_type = serializers.SerializerMethodField()
    changed_by_profile = serializers.SerializerMethodField()
    old_value = serializers.SerializerMethodField()
    new_value = serializers.SerializerMethodField()

    def get_model_type(self, obj) -> str:
        return obj.content_type.model

    def get_changed_by_profile(self, obj) -> dict | None:
        from management.models.support_task import _serialize_user_profile

        return _serialize_user_profile(obj.changed_by)

    def get_old_value(self, obj):
        return self._resolve_value(obj.value_model, obj.old_value)

    def get_new_value(self, obj):
        return self._resolve_value(obj.value_model, obj.new_value)

    def _resolve_value(self, model_label, value):
        if model_label and model_label in _RESOLVABLE_MODELS and value is not None:
            from django.apps import apps

            try:
                app_label, model_name = model_label.split(".", 1)
                model_cls = apps.get_model(app_label, model_name)
                instance = model_cls.objects.select_related("profile").get(pk=value)
                return _serialize_resolved(model_label, instance)
            except Exception:
                return value
        return value

    class Meta:
        model = ObjectHistory
        fields = ["id", "model_type", "changed_by_profile", "changed_at", "type", "field", "old_value", "new_value"]
