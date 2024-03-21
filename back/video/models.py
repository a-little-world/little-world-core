from django.db import models
from django.db.models import Q
from uuid import uuid4

class LiveKitRoom(models.Model):
    
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    u1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u1_livekit_room")
    u2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u2_livekit_room")
    
    @classmethod
    def get_room(cls, user1, user2):
        return cls.objects.get(Q(u1=user1, u2=user2) | Q(u1=user2, u2=user1))
    

class LivekitSession(models.Model):
    
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    u1 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u1_livekit_session")
    u2 = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="u2_livekit_session")
    
    events = models.JSONField(default=list)
    