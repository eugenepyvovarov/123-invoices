import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


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


class ApiToken(models.Model):
    """Account-owned bearer token stored as a one-way hash."""

    TOKEN_PREFIX = 'inv'
    TOKEN_RANDOM_BYTES = 32

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='api_tokens',
    )
    name = models.CharField(max_length=120)
    prefix = models.CharField(max_length=12, db_index=True)
    secret_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['owner__id', 'name', 'id']

    def __str__(self):
        return f"{self.name} ({self.prefix})"

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def is_active(self):
        return not self.is_revoked and not self.is_expired

    @classmethod
    def make_secret_hash(cls, token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @classmethod
    def issue(cls, *, owner, name, expires_at=None):
        prefix = secrets.token_hex(4)
        random_value = secrets.token_urlsafe(cls.TOKEN_RANDOM_BYTES)
        token = f"{cls.TOKEN_PREFIX}_{prefix}_{random_value}"
        instance = cls.objects.create(
            owner=owner,
            name=name,
            prefix=prefix,
            secret_hash=cls.make_secret_hash(token),
            expires_at=expires_at,
        )
        return instance, token

    @classmethod
    def parse_token(cls, token):
        parts = (token or '').split('_', 2)
        if len(parts) != 3 or parts[0] != cls.TOKEN_PREFIX or not parts[1] or not parts[2]:
            return None
        return parts[1]

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])

    def revoke(self):
        if not self.revoked_at:
            self.revoked_at = timezone.now()
            self.save(update_fields=['revoked_at'])
