from django.contrib import admin
from patenmatch.models import PatenmatchUser, PatenmatchOrganization


@admin.register(PatenmatchUser)
class PatenmatchUserAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "postal_code", "email", "support_for")

    search_fields = (
        "email",
        "postal_code",
    )


@admin.register(PatenmatchOrganization)
class PatenmatchOrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "postal_code", "contact_email")

    search_fields = (
        "name",
        "postal_code",
    )
