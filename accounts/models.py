from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Extendable profile for per-user preferences."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    display_timezone = models.CharField(max_length=64, blank=True)
    expense_ai_provider_base_url = models.URLField(blank=True)
    expense_ai_model_name = models.CharField(max_length=120, blank=True)
    expense_ai_api_key = models.CharField(max_length=255, blank=True)
    default_company = models.ForeignKey(
        'invoices.Company',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='default_for_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__id']

    def __str__(self):
        return f"Profile<{self.user_id}>"

    @property
    def has_expense_ai_api_key(self):
        return bool(self.expense_ai_api_key)

    @property
    def masked_expense_ai_api_key(self):
        if not self.expense_ai_api_key:
            return ''
        return '••••••••'

    def has_complete_expense_ai_settings(self):
        return bool(
            self.expense_ai_provider_base_url
            and self.expense_ai_model_name
            and self.expense_ai_api_key
        )
