from django.db import models


class PostCallReview(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey("management.User", on_delete=models.SET_NULL, null=True, blank=True)
    live_session = models.ForeignKey("video.LivekitSession", on_delete=models.SET_NULL, null=True, blank=True)
    review = models.TextField(null=True, blank=True)
    rating = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.user and self.live_session:
            return self.user.email + " - " + self.live_session.uuid + " - " + str(self.rating)
        else:
            return "No user or live session" + " - " + str(self.rating)
