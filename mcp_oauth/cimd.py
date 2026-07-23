from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from oauth2_provider.models import get_application_model


class CIMDError(ValueError):
    def __init__(self, error: str, description: str):
        super().__init__(description)
        self.error = error
        self.description = description


@dataclass(frozen=True)
class ClientMetadata:
    client_id: str
    client_name: str
    redirect_uris: tuple[str, ...]


def ensure_cimd_client(client_id: str | None, redirect_uri: str | None = None):
    """Create a public OAuth app from CIMD metadata when no pre-registered client exists."""
    if not client_id or not _is_url_client_id(client_id):
        return None

    Application = get_application_model()
    existing = Application.objects.filter(client_id=client_id).first()
    if existing is not None:
        return existing

    metadata = resolve_client_metadata(client_id)
    if redirect_uri and redirect_uri not in metadata.redirect_uris:
        raise CIMDError('invalid_request', 'The redirect_uri is not registered in the client metadata document.')

    return Application.objects.create(
        name=metadata.client_name,
        client_id=metadata.client_id,
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=' '.join(metadata.redirect_uris),
    )


def resolve_client_metadata(client_id: str) -> ClientMetadata:
    cache_key = f'mcp-oauth-cimd:{client_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return ClientMetadata(**cached)

    _validate_metadata_url(client_id)
    document = _fetch_metadata_document(client_id)
    metadata = _parse_metadata(client_id, document)
    cache.set(
        cache_key,
        {
            'client_id': metadata.client_id,
            'client_name': metadata.client_name,
            'redirect_uris': metadata.redirect_uris,
        },
        getattr(settings, 'MCP_OAUTH_CIMD_CACHE_SECONDS', 3600),
    )
    return metadata


def _is_url_client_id(client_id: str) -> bool:
    return urlparse(client_id).scheme != ''


def _fetch_metadata_document(client_id: str) -> dict:
    timeout = getattr(settings, 'MCP_OAUTH_CIMD_TIMEOUT_SECONDS', 3)
    max_bytes = getattr(settings, 'MCP_OAUTH_CIMD_MAX_BYTES', 32768)
    request = Request(client_id, headers={'Accept': 'application/json'})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if content_type != 'application/json' and not content_type.endswith('+json'):
                raise CIMDError('invalid_client_metadata', 'Client metadata must be served as JSON.')
            body = response.read(max_bytes + 1)
    except CIMDError:
        raise
    except (OSError, URLError) as exc:
        raise CIMDError('invalid_client_metadata', 'Client metadata could not be fetched.') from exc

    if len(body) > max_bytes:
        raise CIMDError('invalid_client_metadata', 'Client metadata document is too large.')
    try:
        parsed = json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CIMDError('invalid_client_metadata', 'Client metadata is not valid JSON.') from exc
    if not isinstance(parsed, dict):
        raise CIMDError('invalid_client_metadata', 'Client metadata must be a JSON object.')
    return parsed


def _parse_metadata(client_id: str, document: dict) -> ClientMetadata:
    if document.get('client_id') != client_id:
        raise CIMDError('invalid_client_metadata', 'Client metadata client_id must exactly match the requested client_id.')
    redirect_uris = document.get('redirect_uris')
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise CIMDError('invalid_client_metadata', 'Client metadata must include redirect_uris.')
    normalized_redirects = []
    for redirect_uri in redirect_uris:
        if not isinstance(redirect_uri, str):
            raise CIMDError('invalid_client_metadata', 'Client redirect URIs must be strings.')
        _validate_redirect_uri(redirect_uri)
        normalized_redirects.append(redirect_uri)

    client_name = document.get('client_name') or urlparse(client_id).hostname or client_id
    if not isinstance(client_name, str):
        client_name = urlparse(client_id).hostname or client_id
    return ClientMetadata(
        client_id=client_id,
        client_name=_safe_display_name(client_name),
        redirect_uris=tuple(normalized_redirects),
    )


def _safe_display_name(value: str) -> str:
    collapsed = ' '.join(value.split())
    return collapsed[:120] or 'MCP client'


def _validate_metadata_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise CIMDError('invalid_client', 'CIMD client_id must be an HTTPS URL.')
    _reject_unsafe_host(parsed.hostname)


def _validate_redirect_uri(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.fragment or parsed.username or parsed.password:
        raise CIMDError('invalid_client_metadata', 'Redirect URIs must be safe HTTPS URLs without fragments or credentials.')
    _reject_unsafe_host(parsed.hostname)


def _reject_unsafe_host(hostname: str) -> None:
    normalized = hostname.strip().rstrip('.').lower()
    if normalized in {'localhost', 'localhost.localdomain'} or normalized.endswith('.localhost'):
        raise CIMDError('invalid_client_metadata', 'Localhost and private-network hosts are not allowed.')

    addresses: list[str] = []
    try:
        ipaddress.ip_address(normalized)
        addresses.append(normalized)
    except ValueError:
        try:
            addresses.extend(_resolve_host_addresses(normalized))
        except OSError:
            addresses = []

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise CIMDError('invalid_client_metadata', 'Localhost and private-network hosts are not allowed.')


def _resolve_host_addresses(hostname: str) -> list[str]:
    return list({info[4][0] for info in socket.getaddrinfo(hostname, None)})
