from django.contrib import admin
from django.utils.safestring import mark_safe
from django.conf import settings
from .models import EmailLog
from .mails import get_mail_data_by_name, encode_mail_params


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("receiver", "sucess", "view_mail", "template", "time", "sender", "data")

    readonly_fields = ("view_mail",)

    search_fields = ("receiver__email",)

    def view_mail(self, obj):
        try:
            email_params = obj.data["params"]
            template_name = obj.template
            print("Template: " + str(template_name), email_params)
            mail_meta = get_mail_data_by_name(template_name)
            encoded_mail_data = encode_mail_params(email_params)
            url = f"{settings.BASE_URL}/emails/{template_name}/{encoded_mail_data}"
            return mark_safe(f'<a href="{url}" target="_blank" rel="noopener noreferrer" >view</a>')
        except:
            return mark_safe("error")
