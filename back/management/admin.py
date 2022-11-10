from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from . import models

from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin


@admin.register(models.state.State)
class StateAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'user_form_state')
    search_fields = ('user', 'created_at', 'user_form_state')
    ordering = ('user', 'created_at')


class StateAdminInline(admin.TabularInline):
    model = models.state.State


@admin.register(models.user.User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password')}), (_('Personal info'), {
            'fields': ('first_name', 'last_name')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        #("Matching", {"fields" : ("user_matches")})
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )
    list_display = ('email', 'last_login', 'date_joined',
                    'first_name', 'last_name', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email', 'is_staff')

    inlines = [
        StateAdminInline
    ]
