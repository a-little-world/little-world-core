from django.contrib import admin
from .models import Event

# Register your models here.


@admin.register(Event)
class StateAdmin(admin.ModelAdmin):
    list_display = ('_abr_hash', 'name', 'type', 'caller',
                    'time', 'tags', 'func', 'metadata')
    search_fields = ('_abr_hash', 'name', 'type', 'caller',
                     'time', 'tags', 'func', 'metadata')
