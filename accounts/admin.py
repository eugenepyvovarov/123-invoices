from django.contrib import admin

from accounts.models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_timezone", "created_at", "updated_at")
    search_fields = ("user__email",)
