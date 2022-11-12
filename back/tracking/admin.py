from django.contrib import admin
from .models import Event

# Register your models here.


@admin.register(Event)
class StateAdmin(admin.ModelAdmin):
    list_display = ('hash', 'time', 'caller', 'type')
    search_fields = ('hash', 'time', 'caller', 'type')
