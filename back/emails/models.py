from django.db import models
from rest_framework import serializers
from management.models import User


class EmailLog(models.Model):
    # We set on_delete SET_NULL so these logges are not deleted when a user is deleted and vice verca
    sender = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='sender')
    receiver = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='receiver')

    # The time of this log creation, should be roughly equivaent to send time
    time = models.DateTimeField(auto_now_add=True)

    template = models.CharField(max_length=255, blank=True)

    # This marks wheather or not the code to send the email as trown an error
    sucess = models.BooleanField(default=False)

    # hash as wike like to have everywhere :)

    # For this we always expect:
    # template: '...html', email_rendered_html: '...html_str', kwargs: kwargs for creating the mail
    data = models.JSONField()


class EmailLogSerializer(serializers.ModelSerializer):

    class Meta:
        model = EmailLog
        fields = '__all__'
