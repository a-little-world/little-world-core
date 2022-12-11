from django.db import models as dj_models
from martor.widgets import AdminMartorWidget
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django import forms
from phonenumber_field.widgets import PhoneNumberPrefixWidget
from . import models


@admin.register(models.backend_state.BackendState)
class BackendStateAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'hash', 'meta', 'created_at')


@admin.register(models.community_events.CommunityEvent)
class CommunityEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'active', 'description',
                    'time', 'frequency', 'link')


@admin.register(models.matching_scores.MatchinScore)
class DirectionalMatchinScores(admin.ModelAdmin):
    list_display = ('from_usr', 'current_score',
                    'to_usr', 'score', 'matchable', 'messages')
    search_fields = ('from_usr__email', 'from_usr__hash')
    list_filter = ('matchable', 'current_score')
    formfield_overrides = {
        dj_models.TextField: {'widget': AdminMartorWidget},
    }


@admin.register(models.matching_scores.ScoreTableSource)
class ScoreTableAdmin(admin.ModelAdmin):
    list_display = ('tag', 'hash', 'created_at')
    formfield_overrides = {
        dj_models.TextField: {'widget': AdminMartorWidget},
    }


@admin.register(models.state.State)
class StateAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'user_form_state',
                    'matching_state', 'unread_chat_message_count', 'user_category')
    list_editable = ('user_category',)
    search_fields = ('user', 'created_at', 'user_form_state')
    ordering = ('user', 'created_at')


@admin.register(models.Room)
class VideoRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "usr1", "usr2",
                    "active", "updated_at", "created_at")


class StateAdminInline(admin.StackedInline):
    model = models.state.State


@admin.action(description='Match selected')
def make_match_admin(modeladmin, request, queryset):
    pass  # TODO: match selected!
    # queryset.update(status='p')
    modeladmin.message_user(
        request, "Not implemented", level=messages.ERROR)


@admin.register(models.profile.Profile)
class ProfileModelAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'second_name')

    actions = [make_match_admin]


class ProfileModelInline(admin.StackedInline):
    model = models.profile.Profile


@admin.register(models.settings.Settings)
class SettingsModelAdmin(admin.ModelAdmin):
    list_display = ('user', 'language')


class SettingsModelInline(admin.StackedInline):
    model = models.settings.Settings


# TODO: we should make a general class that allowes
class UserFormFilledFilter(admin.SimpleListFilter):
    title = _('User form filled')
    parameter_name = 'is_form_filled'

    def lookups(self, request, model_admin):
        return models.State.UserFormStateChoices.choices

    def queryset(self, request, queryset):
        _val = self.value()
        if not _val:
            return queryset
        return queryset.filter(state__user_form_state=self.value())


class UserCategory(admin.SimpleListFilter):
    title = _('User category')
    parameter_name = 'user_category'

    def lookups(self, request, model_admin):
        return models.State.UserCategoryChoices.choices

    def queryset(self, request, queryset):
        _val = self.value()
        if not _val:
            return queryset
        return queryset.filter(state__user_category=self.value())


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "time_read",
                    "state", "type", "title", "meta")


class NotificationInline(admin.TabularInline):
    model = models.state.Notification


@admin.register(models.user.User)
class UserAdmin(DjangoUserAdmin):

    @admin.display(description='chat')
    def chat_with(self, obj):
        # return HTML link that will not be escaped
        print(obj)
        return mark_safe(
            f'<a href="/admin_chat/?usr_hash={obj.hash}" target="_blank" rel="noopener noreferrer" >open</a>'
        )

    @admin.display(description='matching')
    def show_matching_suggestions(self, obj):
        route = f'/admin/management/matchinscore/?matchable__exact=1&current_score__exact=1&q={obj.hash}&o=-4'
        return mark_safe(
            f'<a href="{route}" target="_blank" rel="noopener noreferrer" >view suggestions</a>'
        )

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super(DjangoUserAdmin, self).get_search_results(
            request, queryset, search_term)
        print("TBS: search therm " + str(search_term))
        return queryset, use_distinct

    inlines = [
        StateAdminInline,
        ProfileModelInline,
        SettingsModelInline,
        NotificationInline,
    ]

    fieldsets = (
        (None, {'fields': ('email', 'password', 'hash',
         'is_active', 'last_login', 'first_name', 'last_name')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )
    list_display = ('_abr_hash', 'email', 'last_login', 'date_joined',
                    'first_name', 'last_name', 'chat_with', 'show_matching_suggestions', 'is_user_form_filled', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'hash')
    # fist & last names are read-only here,
    # the user can change the first / lastnames stored in profile, but not this one!
    readonly_fields = ('hash', 'first_name', 'last_name')
    ordering = ('email', 'is_staff')
    list_filter = (UserFormFilledFilter, UserCategory, 'is_staff',)
