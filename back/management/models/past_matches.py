from django.db import models


class PastMatch(models.Model):
    user1 = models.ForeignKey("management.User", on_delete=models.DO_NOTHING, related_name="user1")

    user2 = models.ForeignKey("management.User", on_delete=models.DO_NOTHING, related_name="user2")

    who_unmatched = models.ForeignKey("management.User", on_delete=models.DO_NOTHING, related_name="unmatcher")

    reason = models.TextField(blank=True, null=True)

    time = models.DateTimeField(auto_now_add=True)
