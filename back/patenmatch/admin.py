from django.contrib import admin
from patenmatch.models import PatenmatchUser, PatenmatchOrganization, PatenmatchOrganizationUserMatching


@admin.register(PatenmatchUser)
class PatenmatchUserAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "postal_code", "email", "support_for", "uuid", "get_email_verification_link", "get_user_status_url", "get_verification_view_url", "list_matched_organizations")

    search_fields = (
        "uuid",
        "email",
        "postal_code",
    )
    
    def get_email_verification_link(self, obj):
        return obj.get_verification_url()
    
    def get_verification_view_url(self, obj):
        return obj.get_verification_view_url()
    
    def list_matched_organizations(self, obj):
        org = PatenmatchOrganizationUserMatching.objects.filter(user=obj)

        if org.exists():
            return f"Matched to {org.first().organization.name}"
        return "No organization matched"
    
    def get_user_status_url(self, obj):
        return f"/en/user/{obj.id}/status?status_access_token={obj.status_access_token}"

@admin.register(PatenmatchOrganizationUserMatching)
class PatenmatchOrganizationUserMatchingAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "created_at", "match_user_name", "match_organization_name", "match_organization_email")

@admin.register(PatenmatchOrganization)
class PatenmatchOrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "postal_code", "contact_email", "list_matched_users")

    search_fields = (
        "name",
        "postal_code",
    )
