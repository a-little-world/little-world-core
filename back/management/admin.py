from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from . import models


@admin.register(models.state.State)
class StateAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'user_form_state')
    search_fields = ('user', 'created_at', 'user_form_state')
    ordering = ('user', 'created_at')


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


class UserFormFilledFilter(admin.SimpleListFilter):
    title = _('User form filled')
    parameter_name = 'is_form_filled'

    def lookups(self, request, model_admin):
        return (
            ('is_filled', _('Form filled')),
            ('is_not_filled', _('Form not filled')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'is_filled':
            return [q for q in queryset if q.is_user_form_filled()]
        if self.value() == 'is_not_filled':
            return [q for q in queryset if not q.is_user_form_filled()]


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
        return mark_safe(
            '<a href="%s">%s</a>' % ("bla", "open")
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
        NotificationInline
    ]

    fieldsets = (
        (None, {'fields': ('email', 'password', 'hash')}),
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
                    'first_name', 'last_name', 'chat_with', 'is_user_form_filled', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'hash')
    ordering = ('email', 'is_staff')
    list_filter = (UserFormFilledFilter, 'is_staff',)
