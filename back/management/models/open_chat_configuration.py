from django.db import models


class OpenChatConfiguration(models.Model):
    user = models.OneToOneField(
        "management.User",
        on_delete=models.CASCADE,
        related_name="open_chat_configuration",
    )
    open_chat_api_key = models.CharField(max_length=512)
    open_chat_user = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"OpenChatConfiguration(user_id={self.user_id})"
