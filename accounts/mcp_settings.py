from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse

from mcp_oauth.validators import normalized_resource


LOCAL_HOSTNAMES = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}


def mcp_connection_context() -> dict:
    """Return non-secret MCP connection details for User settings."""

    resource_url = normalized_resource(getattr(settings, 'MCP_OAUTH_RESOURCE_URL', ''))
    issuer_url = _normalized_issuer(getattr(settings, 'MCP_OAUTH_ISSUER_URL', ''))
    is_local = _is_local_url(resource_url) or _is_local_url(issuer_url)
    is_configured = _is_public_https_url(resource_url) and _is_public_https_url(issuer_url)
    is_debug = bool(getattr(settings, 'DEBUG', False))

    if is_configured:
        status = {
            'key': 'configured',
            'label': 'Configured',
            'message': 'MCP appears configured with public OAuth and resource URLs for this deployment.',
        }
    elif is_local and is_debug:
        status = {
            'key': 'local_development',
            'label': 'Local development',
            'message': 'MCP is using local development URLs. Use public HTTPS values before sharing with external clients.',
        }
    else:
        status = {
            'key': 'not_configured',
            'label': 'Not publicly configured',
            'message': 'MCP is not ready for public client setup because the OAuth issuer or MCP resource URL is missing or local-only.',
        }

    return {
        'resource_url': resource_url,
        'endpoint_url': resource_url,
        'issuer_url': issuer_url,
        'authorization_server_metadata_url': _absolute_url(issuer_url, reverse('mcp_oauth_as_metadata')),
        'protected_resource_metadata_url': _absolute_url(issuer_url, reverse('mcp_oauth_prm')),
        'authorization_url': _absolute_url(issuer_url, reverse('oauth2_provider:authorize')),
        'token_url': _absolute_url(issuer_url, reverse('oauth2_provider:token')),
        'cimd_enabled': bool(getattr(settings, 'MCP_OAUTH_CIMD_ENABLED', True)),
        'scopes': _oauth_scopes(),
        'status': status,
    }


def _normalized_issuer(value: str | None) -> str:
    return str(value or '').strip().rstrip('/')


def _absolute_url(base_url: str, path: str) -> str:
    if not base_url:
        return ''
    return f'{base_url}{path}'


def _oauth_scopes() -> list[dict[str, str]]:
    scopes = getattr(settings, 'OAUTH2_PROVIDER', {}).get('SCOPES', {})
    return [{'name': name, 'description': description} for name, description in scopes.items()]


def _is_local_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    hostname = parsed.hostname or ''
    return hostname.lower() in LOCAL_HOSTNAMES


def _is_public_https_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = parsed.hostname or ''
    return parsed.scheme == 'https' and hostname.lower() not in LOCAL_HOSTNAMES
