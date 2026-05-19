import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from accounts.models import Profile


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def normalize_email(sender, instance, **kwargs):
    """Normalize email addresses and ensure uniqueness."""

    email = (instance.email or '').strip().lower()
    if not email:
        return

    instance.email = email
    if not instance.username:
        instance.username = f"user-{uuid.uuid4().hex[:8]}"

    qs = sender.objects.filter(email=email)
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise ValidationError("A user with that email already exists.")


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if not created:
        return
    Profile.objects.get_or_create(user=instance)
