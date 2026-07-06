from rest_framework import serializers

from invoices.models import Issuer


def accessible_issuers_for_user(user):
    """Return issuers available to an authenticated API account."""
    queryset = Issuer.objects.select_related('company').all()
    if not getattr(user, 'is_authenticated', False):
        return queryset.none()
    if user.is_superuser:
        return queryset
    return queryset.filter(users=user)


def accessible_issuer_ids_for_user(user):
    return accessible_issuers_for_user(user).values_list('id', flat=True)


def validate_writable_issuer(user, issuer):
    if issuer is None:
        raise serializers.ValidationError({'issuer': 'This field is required.'})
    if not accessible_issuers_for_user(user).filter(pk=issuer.pk).exists():
        raise serializers.ValidationError({'issuer': 'Issuer is not available to this account.'})
    return issuer


def require_accessible_issuer_id(user, issuer_id):
    try:
        issuer_id = int(issuer_id)
    except (TypeError, ValueError):
        raise serializers.ValidationError({'issuer': 'Issuer must be a valid ID.'})
    try:
        return accessible_issuers_for_user(user).get(pk=issuer_id)
    except Issuer.DoesNotExist:
        raise serializers.ValidationError({'issuer': 'Issuer is not available to this account.'})
