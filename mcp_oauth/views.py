from __future__ import annotations

import base64
import secrets
from datetime import timezone

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone as django_timezone
from django.views.decorators.csrf import csrf_exempt
from oauth2_provider.models import get_access_token_model

from .validators import configured_resource, normalized_resource


def issuer_url() -> str:
    return str(getattr(settings, 'MCP_OAUTH_ISSUER_URL', '')).rstrip('/')


def absolute_endpoint(path: str) -> str:
    return f'{issuer_url()}{path}'


def oauth_scopes() -> dict[str, str]:
    return getattr(settings, 'OAUTH2_PROVIDER', {}).get('SCOPES', {})


def authorization_server_metadata(request):
    scopes = oauth_scopes()
    return JsonResponse(
        {
            'issuer': issuer_url(),
            'authorization_endpoint': absolute_endpoint(reverse('oauth2_provider:authorize')), 
            'token_endpoint': absolute_endpoint(reverse('oauth2_provider:token')),
            'introspection_endpoint': absolute_endpoint(reverse('mcp_oauth_introspect')),
            'response_types_supported': ['code'],
            'grant_types_supported': ['authorization_code', 'refresh_token'],
            'code_challenge_methods_supported': ['S256'],
            'token_endpoint_auth_methods_supported': ['client_secret_basic', 'client_secret_post', 'none'],
            'scopes_supported': list(scopes.keys()),
            'resource_indicators_supported': True,
            'client_id_metadata_document_supported': True,
        }
    )


def protected_resource_metadata(request):
    return JsonResponse(
        {
            'resource': configured_resource(),
            'authorization_servers': [issuer_url()],
            'scopes_supported': list(oauth_scopes().keys()),
            'bearer_methods_supported': ['header'],
        }
    )


@csrf_exempt
def introspect(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method_not_allowed'}, status=405)
    if not _introspection_auth_allowed(request):
        response = JsonResponse({'error': 'invalid_client'}, status=401)
        response['WWW-Authenticate'] = 'Basic realm="mcp-oauth-introspection"'
        return response

    token_value = request.POST.get('token', '')
    requested_resource = normalized_resource(request.POST.get('resource'))
    if not token_value:
        return JsonResponse({'active': False})

    access_token = (
        get_access_token_model()
        .objects.select_related('application', 'user')
        .filter(token=token_value)
        .first()
    )
    if access_token is None or access_token.expires <= django_timezone.now():
        return JsonResponse({'active': False})

    resource = _token_resource(access_token)
    if requested_resource and requested_resource != resource:
        return JsonResponse({'active': False})

    payload = {
        'active': True,
        'scope': access_token.scope,
        'client_id': access_token.application.client_id if access_token.application else '',
        'token_type': 'Bearer',
        'exp': int(access_token.expires.astimezone(timezone.utc).timestamp()),
        'iss': issuer_url(),
        'aud': resource,
        'resource': resource,
    }
    if access_token.user_id:
        payload['sub'] = str(access_token.user_id)
        payload['username'] = access_token.user.get_username()
    return JsonResponse(payload)


def _token_resource(access_token) -> str:
    binding = getattr(access_token, 'mcp_resource_binding', None)
    return normalized_resource(getattr(binding, 'resource', '') or configured_resource())


def _introspection_auth_allowed(request) -> bool:
    expected = getattr(settings, 'MCP_OAUTH_INTROSPECTION_TOKEN', '')
    if not expected:
        return True
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return secrets.compare_digest(auth_header.removeprefix('Bearer ').strip(), expected)
    if auth_header.startswith('Basic '):
        try:
            decoded = base64.b64decode(auth_header.removeprefix('Basic ').strip()).decode()
        except Exception:
            return False
        _username, _sep, password = decoded.partition(':')
        return secrets.compare_digest(password, expected)
    return False
