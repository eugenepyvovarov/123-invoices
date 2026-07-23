from django.contrib import admin

from .models import AccessTokenResource


@admin.register(AccessTokenResource)
class AccessTokenResourceAdmin(admin.ModelAdmin):
    list_display = ('access_token', 'resource', 'created_at')
    search_fields = ('access_token__token', 'resource')
