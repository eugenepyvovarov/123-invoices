from __future__ import annotations

from django.conf import settings

try:
    from oauth2_provider.oauth2_validators import OAuth2Validator
except ImportError:  # pragma: no cover - dependency is installed in CI/runtime
    OAuth2Validator = object

from .models import AccessTokenResource


class MCPOAuth2Validator(OAuth2Validator):
    """OAuth Toolkit validator with MCP resource-indicator binding."""

    def save_bearer_token(self, token, request, *args, **kwargs):
        super().save_bearer_token(token, request, *args, **kwargs)
        resource = normalized_resource(getattr(request, 'resource', None) or getattr(request, 'resource_indicator', None))
        if not resource:
            resource = normalized_resource(getattr(settings, 'MCP_OAUTH_RESOURCE_URL', ''))
        access_token_value = token.get('access_token') if isinstance(token, dict) else None
        if not access_token_value:
            return
        try:
            access_token = self._get_access_token(access_token_value)
        except Exception:
            return
        AccessTokenResource.objects.update_or_create(
            access_token=access_token,
            defaults={'resource': resource},
        )

    def _get_access_token(self, token_value):
        from oauth2_provider.models import get_access_token_model

        return get_access_token_model().objects.get(token=token_value)


def normalized_resource(resource: str | None) -> str:
    return (resource or '').strip().rstrip('/') + '/' if (resource or '').strip() else ''


def configured_resource() -> str:
    return normalized_resource(getattr(settings, 'MCP_OAUTH_RESOURCE_URL', ''))
