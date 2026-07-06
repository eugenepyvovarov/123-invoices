from django.contrib import admin

from accounts.models import ApiToken, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_timezone", "created_at", "updated_at")
    search_fields = ("user__email",)


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "prefix",
        "created_at",
        "last_used_at",
        "expires_at",
        "revoked_at",
    )
    list_filter = ("created_at", "expires_at", "revoked_at")
    search_fields = ("name", "owner__username", "owner__email", "prefix")
    readonly_fields = ("prefix", "secret_hash", "created_at", "last_used_at", "revoked_at")
