from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from . import models

from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin


@admin.register(models.state.State)
class StateAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'user_form_state')
    search_fields = ('user', 'created_at', 'user_form_state')
    ordering = ('user', 'created_at')


class StateAdminInline(admin.StackedInline):
    model = models.state.State


@admin.register(models.profile.Profile)
class ProfileModelAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'second_name')


class ProfileModelInline(admin.StackedInline):
    model = models.profile.Profile


@admin.register(models.settings.Settings)
class SettingsModelAdmin(admin.ModelAdmin):
    list_display = ('user', 'language')


class SettingsModelInline(admin.StackedInline):
    model = models.settings.Settings


@admin.register(models.user.User)
class UserAdmin(DjangoUserAdmin):
    inlines = [
        StateAdminInline,
        ProfileModelInline,
        SettingsModelInline
    ]

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Permissions'), {
         'fields': ('is_active', 'is_staff', 'is_superuser')}),
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
