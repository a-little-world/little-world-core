from django.db import models
from django.db.models import Q

from back.utils import _double_uuid

from .user import User


def get_rooms_user(user):
    return Room.objects.filter(Q(usr1=user) | Q(usr2=user))


def get_rooms_match(usr1, usr2):
    return get_rooms_user(usr1).filter(Q(usr1=usr2) | Q(usr2=usr2))


class Room(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    """
    This stores the last time the room was used! 
    You may also look for authentication in the tracking logs if you want more detailed infos
    """
    last_time_autenticated = models.DateTimeField(auto_now_add=True)

    hash = models.CharField(max_length=255, default=_double_uuid)

    """
    This stores the room name, this is important for twilio!
    """
    name = models.CharField(max_length=255, default=_double_uuid)

    usr1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="usr1")
    usr2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="usr2")

    """
    This marks weather or not a video rooms is active! 
    If this is set to false ( as it can be done manually by admins )
    then the two users can't enter their video room!
    """
    active = models.BooleanField(default=True)

    def is_active(self):
        return self.active

    @classmethod
    def get_room_by_hash(cls, hash):
        # Room must exists!
        r = cls.objects.filter(name=hash)
        assert r.exists() and r.count() == 1, "Room doesn't seem to exist"
        return r.first()
