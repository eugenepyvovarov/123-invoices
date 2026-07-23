from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from typing import Any

import httpx

from .config import MCPConfig
from .errors import MCPConfigurationError


AUTH_ERROR_PAYLOAD = {
    "code": "mcp_authentication_failed",
    "message": "A valid OAuth bearer token is required to use the invoices MCP endpoint.",
}


def build_auth_settings(config: MCPConfig):
    try:
        from mcp.server.auth.settings import AuthSettings
    except ImportError as exc:  # pragma: no cover - covered by dependency installation in CI
        raise MCPConfigurationError("The MCP SDK auth module is not installed.") from exc

    return AuthSettings(
        issuer_url=config.oauth_issuer_url,
        resource_server_url=config.oauth_resource_url,
        required_scopes=[],
    )


class InvoicesTokenVerifier:
    """MCP SDK TokenVerifier backed by OAuth introspection or test-only probe tokens."""

    def __init__(self, config: MCPConfig, client: httpx.AsyncClient | None = None):
        self.config = config
        self.client = client

    async def verify_token(self, token: str):
        if not token:
            return None

        if token in self.config.auth_test_tokens:
            return self._access_token(
                token=token,
                client_id="mcp-ci-probe",
                scopes=self.config.oauth_scopes,
                expires_at=int(time.time()) + 300,
                subject="mcp-ci-probe",
                claims={"iss": self.config.oauth_issuer_url, "aud": self.config.oauth_resource_url},
            )

        if not self.config.oauth_introspection_url:
            return None


        close_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.config.timeout_seconds)
        try:
            response = await client.post(
                self.config.oauth_introspection_url,
                data={"token": token, "resource": self.config.oauth_resource_url},
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError:
            return None
        finally:
            if close_client:
                await client.aclose()

        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        return self.access_token_from_introspection(token, payload, self.config)

    @classmethod
    def access_token_from_introspection(cls, token: str, payload: Mapping[str, Any], config: MCPConfig):
        if payload.get("active") is not True:
            return None
        expires_at = _optional_int(payload.get("exp"))
        if expires_at is not None and expires_at < int(time.time()):
            return None
        issuer = payload.get("iss")
        if issuer and str(issuer).rstrip("/") != config.oauth_issuer_url.rstrip("/"):
            return None
        if not _audience_matches(payload, config.oauth_resource_url):
            return None

        return cls._access_token(
            token=token,
            client_id=str(payload.get("client_id") or payload.get("azp") or "oauth-client"),
            scopes=_parse_scope(payload.get("scope") or payload.get("scopes")),
            expires_at=expires_at,
            subject=str(payload.get("sub")) if payload.get("sub") else None,
            claims={"iss": issuer, "aud": payload.get("aud") or payload.get("resource")},
        )

    @staticmethod
    def _access_token(**kwargs):
        try:
            from mcp.server.auth.provider import AccessToken
        except ImportError as exc:  # pragma: no cover - covered by dependency installation in CI
            raise MCPConfigurationError("The MCP SDK auth provider module is not installed.") from exc

        return AccessToken(**kwargs)


def required_scope_for_tool(tool_name: str, config: MCPConfig) -> str:
    if tool_name in {"create_draft_invoice", "update_draft_invoice"}:
        return config.draft_write_scope
    if tool_name == "finalize_invoice":
        return config.finalize_scope
    if tool_name in {"generate_invoice_pdf", "get_invoice_artifact"}:
        return config.artifact_read_scope
    return config.read_scope


def has_required_scope(tool_name: str, config: MCPConfig) -> bool:
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token
    except ImportError:  # pragma: no cover - local unit tests may run without MCP installed
        return True

    access_token = get_access_token()
    if access_token is None:
        return True
    return required_scope_for_tool(tool_name, config) in set(access_token.scopes or [])


def _parse_scope(value: Any) -> list[str]:
    if isinstance(value, str):
        return [scope for scope in value.split() if scope]
    if isinstance(value, Iterable):
        return [str(scope) for scope in value if str(scope)]
    return []


def _audience_matches(payload: Mapping[str, Any], resource_url: str) -> bool:
    candidates = payload.get("aud") or payload.get("resource")
    if isinstance(candidates, str):
        candidates = [candidates]
    if not isinstance(candidates, Iterable):
        return False
    normalized_resource = resource_url.rstrip("/")
    return any(str(candidate).rstrip("/") == normalized_resource for candidate in candidates)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
