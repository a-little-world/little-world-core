import uuid

from django.db import models
from rest_framework import serializers


class PreMatchingAppointment(models.Model):
    user = models.ForeignKey("management.User", on_delete=models.SET_NULL, null=True)

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    created = models.DateTimeField(auto_now_add=True)

    sms_task = models.TextField(default="")

    #: cal.com's booking `uid`. Lets a later reschedule/cancel webhook find the row it
    #: refers to (and stops a delayed cancel for a superseded booking from deleting a
    #: newer one).
    calcom_booking_uid = models.CharField(max_length=255, blank=True, default="")

    @classmethod
    def get_current_for_user(cls, user):
        """The most recently created appointment for a user.

        Deliberately ordered: a bare ``filter(user=user).first()`` is DB-order
        dependent and can pick an arbitrary stale duplicate.
        """
        return cls.objects.filter(user=user).order_by("-created").first()


class PreMatchingAppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreMatchingAppointment
        fields = ["uuid", "start_time", "end_time", "created"]
