from django.contrib import admin
from patenmatch.models import PatenmatchUser, PatenmatchOrganization


@admin.register(PatenmatchUser)
class PatenmatchUserAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "postal_code", "email", "support_for", "uuid", "get_email_verification_link", "get_user_status_url")

    search_fields = (
        "uuid",
        "email",
        "postal_code",
    )
    
    def get_email_verification_link(self, obj):
        return obj.get_verification_url()
    
    def get_user_status_url(self, obj):
        return f"/en/user/{obj.id}/status?status_access_token={obj.status_access_token}"


@admin.register(PatenmatchOrganization)
class PatenmatchOrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "postal_code", "contact_email")

    search_fields = (
        "name",
        "postal_code",
    )
