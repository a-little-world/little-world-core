from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
import concurrent.futures
from asgiref.sync import sync_to_async, async_to_sync
import base64
from uuid import uuid4
from channels.layers import get_channel_layer
from threading import Thread


class Connections(models.Model):
    """
    Model is created for every deveice a user connects with 
    """
    user = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="active_connection_user")
    channel_name = models.CharField(max_length=255)

    active = models.BooleanField(default=True)
    
    time_joined = models.DateTimeField(auto_now_add=True)
    time_left = models.DateTimeField(null=True, blank=True)


class ConsumerConnections(models.Model):
    """
    Model is created when a user connects, one model per user.
    This model is only created once and then stays created.
    """
    user = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="consumer_connections_user")
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    
    connections = models.ManyToManyField("Connections", related_name="consumer_connections_connections")
    
    @classmethod
    def get_or_create(cls, user, escalate = False):
        active_connections = cls.objects.filter(user=user)
        if active_connections.exists():
            return active_connections.first()
        else:
            if escalate:
                raise Exception("Consumer connection should already exist!")
            return cls.objects.create(user=user)
        
    def connect_device(self, channel_name):
        self.connections.create(user=self.user, channel_name=channel_name)
        
    def disconnect_device(self, channel_name):
        device = self.connections.filter(channel_name=channel_name).first()
        device.active = False
        device.time_left = timezone.now()
        device.save()
        self.connections.remove(device)
        self.save()
        
    @classmethod
    def has_active_connections(cls, user):
        return cls.objects.filter(user=user, connections__active=True).exists()
        
    @classmethod
    def async_notify_connections(cls, user, event="reduction", payload={}):
        """
        Runs notify connections in a seperate thread
        """
        # TODO: this can cause process usage and cleanup issues can it?
        thread = Thread(target=cls.notify_connections, args=(user, event, payload))
        thread.start()
        
    @classmethod
    def notify_connections(cls, user, event="reduction", payload={}):
        
        consumer_connection = cls.get_or_create(user)
        channel_layer = get_channel_layer()
        
        async_to_sync(channel_layer.group_send)(str(consumer_connection.uuid), {
            "type": "broadcast_message",
            "data": {
                "event": event,
                "payload": payload
            }
        })
        
    def notify_device(self, channel_name):
        pass # TODO: to nofiy a specific user device