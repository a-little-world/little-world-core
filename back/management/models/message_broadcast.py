from django.db import models


class MessageBroadcastList(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    users = models.ManyToManyField("management.User", related_name="recipient_lists")
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
