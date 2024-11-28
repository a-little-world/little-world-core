from django.contrib.sessions.models import Session
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from management import models
from management.models import question_deck, scores, pre_matching_appointment, newsletter, stats
from hijack.contrib.admin import HijackUserAdminMixin
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponse
import base64

@admin.register(stats.Statistic)
class StatisticAdmin(admin.ModelAdmin):
    list_display = ("created_at", "updated_at", "kind")


@admin.register(models.backend_state.BackendState)
class BackendStateAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "hash", "meta", "created_at")


@admin.register(models.help_message.HelpMessage)
class HelpMessageStateAdmin(admin.ModelAdmin):
    list_display = ("user", "message", "created_at", "hash", "attachment1_links", "attachment2_links", "attachment3_links")

    def attachment1_links(self, obj):
        return self._get_attachment_links(obj, 'attachment1')
    attachment1_links.short_description = 'Attachment 1'

    def attachment2_links(self, obj):
        return self._get_attachment_links(obj, 'attachment2')
    attachment2_links.short_description = 'Attachment 2'

    def attachment3_links(self, obj):
        return self._get_attachment_links(obj, 'attachment3')
    attachment3_links.short_description = 'Attachment 3'

    def _get_attachment_links(self, obj, field_name):
        attachment = getattr(obj, field_name)
        if attachment:
            download_url = reverse('admin:download_attachment', args=[obj.id, field_name])
            preview_url = reverse('admin:preview_attachment', args=[obj.id, field_name])
            return format_html(
                '<a href="{}" target="_blank">Preview</a> | <a href="{}">Download</a>',
                preview_url, download_url
            )
        return "No attachment"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<int:object_id>/attachment/<str:field_name>/', 
                 self.admin_site.admin_view(self.download_attachment), 
                 name='download_attachment'),
            path('<int:object_id>/preview/<str:field_name>/', 
                 self.admin_site.admin_view(self.preview_attachment), 
                 name='preview_attachment'),
        ]
        return custom_urls + urls

    def download_attachment(self, request, object_id, field_name):
        obj = self.get_object(request, object_id)
        if obj is None:
            return HttpResponse("Object not found", status=404)
        
        attachment = getattr(obj, field_name)
        if attachment is None:
            return HttpResponse("Attachment not found", status=404)
        
        response = HttpResponse(attachment, content_type='image/jpeg')
        response['Content-Disposition'] = f'attachment; filename="{field_name}.jpeg"'
        return response

    def preview_attachment(self, request, object_id, field_name):
        obj = self.get_object(request, object_id)
        if obj is None:
            return HttpResponse("Object not found", status=404)
        
        attachment = getattr(obj, field_name)
        if attachment is None:
            return HttpResponse("Attachment not found", status=404)
        
        image_data = base64.b64encode(attachment).decode('utf-8')
        return HttpResponse(f'<img src="data:image/jpeg;base64,{image_data}" style="max-width: 100%;">')

@admin.register(models.settings.EmailSettings)
class EmailSettingsAdmin(admin.ModelAdmin):
    list_display = ("hash", "unsubscibed_options")


@admin.register(models.banner.Banner)
class CommunityEventAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "active", "text", "cta_1_text", "cta_2_text")

@admin.register(models.community_events.CommunityEvent)
class CommunityEventAdmin(admin.ModelAdmin):
    list_display = ("title", "active", "description", "time", "frequency", "link")


@admin.register(models.news_and_updates.NewsItem)
class NewsItemAdmin(admin.ModelAdmin):
    list_display = ("title", "active", "description", "time", "link")


@admin.register(models.matches.Match)
class MatchModelAdmin(admin.ModelAdmin):
    list_display = ("uuid", "created_at", "updated_at", "user1", "user2")


@admin.register(models.state.State)
class StateAdmin(HijackUserAdminMixin, admin.ModelAdmin):
    list_display = ("user", "created_at", "user_form_state", "matching_state", "user_category", "tags")
    list_editable = (
        "user_category",
        "tags",
    )
    search_fields = ("user", "created_at", "user_form_state")
    ordering = ("user", "created_at")

    def get_hijack_user(self, obj):
        return obj.user


@admin.register(models.rooms.Room)
class VideoRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "usr1", "usr2", "active", "updated_at", "created_at")


class StateAdminInline(admin.StackedInline):
    model = models.state.State


@admin.action(description="Match selected")
def make_match_admin(modeladmin, request, queryset):
    pass  # TODO: match selected!
    # queryset.update(status='p')
    modeladmin.message_user(request, "Not implemented", level=messages.ERROR)


@admin.register(models.profile.Profile)
class ProfileModelAdmin(admin.ModelAdmin):
    list_display = ("user", "first_name", "second_name", "user_type", "birth_year", "description", "notify_channel")

    actions = [make_match_admin]


class ProfileModelInline(admin.StackedInline):
    model = models.profile.Profile


@admin.register(models.settings.Settings)
class SettingsModelAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "email_settings")


class SettingsModelInline(admin.StackedInline):
    model = models.settings.Settings


# TODO: we should make a general class that allowes
class UserFormFilledFilter(admin.SimpleListFilter):
    title = _("User form filled")
    parameter_name = "is_form_filled"

    def lookups(self, request, model_admin):
        return models.state.State.UserFormStateChoices.choices

    def queryset(self, request, queryset):
        _val = self.value()
        if not _val:
            return queryset
        return queryset.filter(state__user_form_state=self.value())


class UserCategory(admin.SimpleListFilter):
    title = _("User category")
    parameter_name = "user_category"

    def lookups(self, request, model_admin):
        return models.state.State.UserCategoryChoices.choices

    def queryset(self, request, queryset):
        _val = self.value()
        if not _val:
            return queryset
        return queryset.filter(state__user_category=self.value())


@admin.register(models.notifications.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "time_read", "state", "type", "title", "meta")


class NotificationInline(admin.TabularInline):
    model = models.state.Notification


@admin.register(models.user.User)
class UserAdmin(HijackUserAdminMixin, DjangoUserAdmin):
    def get_hijack_user(self, obj):
        return obj

    @admin.display(description="chat")
    def chat_with(self, obj):
        # return HTML link that will not be escaped
        print(obj)
        return mark_safe(f'<a href="/admin_chat/?usr_hash={obj.hash}" target="_blank" rel="noopener noreferrer" >open</a>')

    @admin.display(description="matching")
    def show_matching_suggestions(self, obj):
        route = f"/admin/management/matchinscore/?matchable__exact=1&current_score__exact=1&q={obj.hash}&o=-4"
        return mark_safe(f'<a href="{route}" target="_blank" rel="noopener noreferrer" >view suggestions</a>')

    @admin.display(description="activity")
    def view_tracked_activity(self, obj):
        url = f"/admin/tracking/event/?q={obj.hash}&o=-5"
        return mark_safe(f'<a href="{url}" target="_blank" rel="noopener noreferrer" >view tracked activity</a>')

    @admin.display(description="existing_matches")
    def show_matches_in_panel(self, obj):
        route = f"/admin_panel/?matches={obj.hash}"
        return mark_safe(f'<a href="{route}" target="_blank" rel="noopener noreferrer" >show user and matches in admin panel</a>')

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super(DjangoUserAdmin, self).get_search_results(request, queryset, search_term)
        print("TBS: search therm " + str(search_term))
        return queryset, use_distinct

    inlines = [
        StateAdminInline,
        ProfileModelInline,
        SettingsModelInline,
        NotificationInline,
    ]

    fieldsets = ((None, {"fields": ("email", "password", "hash", "is_active", "last_login", "first_name", "last_name")}),)
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    list_display = ("_abr_hash", "email", "last_login", "date_joined", "first_name", "last_name", "chat_with", "show_matching_suggestions", "show_matches_in_panel", "view_tracked_activity", "is_user_form_filled", "is_staff", "username")
    search_fields = ("email", "first_name", "last_name", "hash")
    # fist & last names are read-only here,
    # the user can change the first / lastnames stored in profile, but not this one!
    readonly_fields = ("hash", "first_name", "last_name")
    ordering = ("email", "is_staff")
    list_filter = (
        UserFormFilledFilter,
        UserCategory,
        "is_staff",
    )


@admin.register(models.unconfirmed_matches.ProposedMatch)
class ProposedMatchAdmin(admin.ModelAdmin):
    list_display = ("hash", "user1", "user2", "closed", "expires_at")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    def _session_data(self, obj):
        return obj.get_decoded()

    list_display = ["session_key", "_session_data", "expire_date"]


@admin.register(question_deck.QuestionCardsDeck)
class QuestionCardDeckAdmin(admin.ModelAdmin):
    list_display = ("uuid", "user")


@admin.register(question_deck.QuestionCardCategories)
class QuestionCardCategoryAdmin(admin.ModelAdmin):
    list_display = ("uuid", "ref_id", "content")


@admin.register(question_deck.QuestionCard)
class QuestionCardAdmin(admin.ModelAdmin):
    list_display = ("uuid", "ref_id", "category", "content")


@admin.register(scores.TwoUserMatchingScore)
class TwoUserMatchingScoreAdmin(admin.ModelAdmin):
    list_display = ("user1", "user2", "matchable", "score", "latest_update")


@admin.register(pre_matching_appointment.PreMatchingAppointment)
class PreMatchingAppointmentAdmin(admin.ModelAdmin):
    list_display = ("user", "start_time", "end_time", "created")


@admin.register(newsletter.NewsLetterSubscription)
class NewsLetterSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("email", "two_step_verification", "created", "active")
