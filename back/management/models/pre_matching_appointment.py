from django.db import models
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
import uuid

class PreMatchingAppointment(models.Model):
    user = models.ForeignKey("management.User", on_delete=models.SET_NULL, null=True)
    
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    created = models.DateTimeField(auto_now_add=True)
    
class PreMatchingAppointmentSerializer(serializers.ModelSerializer):

    class Meta:
        model = PreMatchingAppointment
        fields = ['uuid', 'start_time', 'end_time', 'created']
