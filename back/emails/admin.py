from django.contrib import admin
from django.utils.safestring import mark_safe
from django.conf import settings
from emails.models import EmailLog, DynamicTemplate
from emails.mails import get_mail_data_by_name, encode_mail_params

@admin.register(DynamicTemplate)
class DynamicTemplateAdmin(admin.ModelAdmin):
    list_display = ("uuid", "template_name", "subject", "content")

    search_fields = ("template_name", )

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("receiver", "sucess", "view_mail", "template", "time", "sender", "data")

    readonly_fields = ("view_mail",)

    search_fields = ("receiver__email",)

    def view_mail(self, obj):
        
        if obj.log_version == 1:
            url = f"{settings.BASE_URL}/api/matching/emails/logs/{obj.id}/"
            return mark_safe(f'<a href="{url}" target="_blank" rel="noopener noreferrer" >view</a>')
        else:
            return mark_safe("<p>This is a V1 email we depricated in favor of V2 emails! These old emails cannot be viewed anymore!</p>")