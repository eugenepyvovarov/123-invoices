from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping
from urllib.parse import urljoin

from .errors import MCPConfigurationError


DEFAULT_ENDPOINT_PATH = "/mcp/"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
DEFAULT_READ_SCOPE = "invoices:mcp:read"
DEFAULT_DRAFT_WRITE_SCOPE = "invoices:mcp:draft:write"
DEFAULT_FINALIZE_SCOPE = "invoices:mcp:finalize"
DEFAULT_ARTIFACT_READ_SCOPE = "invoices:mcp:artifact:read"


@dataclass(frozen=True, slots=True)
class MCPConfig:
    api_base_url: str
    api_token: str
    oauth_issuer_url: str
    oauth_resource_url: str
    oauth_introspection_url: str | None = None
    auth_test_tokens: tuple[str, ...] = ()
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    endpoint_path: str = DEFAULT_ENDPOINT_PATH
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    public_url: str | None = None
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES
    read_scope: str = DEFAULT_READ_SCOPE
    draft_write_scope: str = DEFAULT_DRAFT_WRITE_SCOPE
    finalize_scope: str = DEFAULT_FINALIZE_SCOPE
    artifact_read_scope: str = DEFAULT_ARTIFACT_READ_SCOPE

    @property
    def normalized_api_base_url(self) -> str:
        return self.api_base_url.rstrip("/") + "/"

    def api_url(self, path: str) -> str:
        return urljoin(self.normalized_api_base_url, path.lstrip("/"))

    @property
    def oauth_scopes(self) -> tuple[str, ...]:
        return (self.read_scope, self.draft_write_scope, self.finalize_scope, self.artifact_read_scope)


def load_config(env: Mapping[str, str] | None = None) -> MCPConfig:
    env = environ if env is None else env
    api_base_url = _required(env, "INVOICES_MCP_API_BASE_URL")
    api_token = _required(env, "INVOICES_MCP_API_TOKEN")
    endpoint_path = _normalize_endpoint_path(env.get("INVOICES_MCP_ENDPOINT_PATH", DEFAULT_ENDPOINT_PATH))
    public_url = env.get("INVOICES_MCP_PUBLIC_URL") or None
    resource_url = env.get("INVOICES_MCP_OAUTH_RESOURCE_URL") or public_url
    if not resource_url:
        raise MCPConfigurationError("INVOICES_MCP_OAUTH_RESOURCE_URL or INVOICES_MCP_PUBLIC_URL is required for OAuth resource-server auth.")

    return MCPConfig(
        api_base_url=api_base_url,
        api_token=api_token,
        oauth_issuer_url=_required(env, "INVOICES_MCP_OAUTH_ISSUER_URL"),
        oauth_resource_url=resource_url,
        oauth_introspection_url=env.get("INVOICES_MCP_OAUTH_INTROSPECTION_URL") or None,
        auth_test_tokens=_parse_optional_tokens(env.get("INVOICES_MCP_AUTH_TEST_TOKENS", "")),
        host=env.get("INVOICES_MCP_HOST", DEFAULT_HOST),
        port=_parse_int(env, "INVOICES_MCP_PORT", DEFAULT_PORT, minimum=1, maximum=65535),
        endpoint_path=endpoint_path,
        timeout_seconds=_parse_float(env, "INVOICES_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=0.1),
        public_url=public_url,
        max_artifact_bytes=_parse_int(env, "INVOICES_MCP_MAX_ARTIFACT_BYTES", DEFAULT_MAX_ARTIFACT_BYTES, minimum=1),
        read_scope=env.get("INVOICES_MCP_SCOPE_READ", DEFAULT_READ_SCOPE),
        draft_write_scope=env.get("INVOICES_MCP_SCOPE_DRAFT_WRITE", DEFAULT_DRAFT_WRITE_SCOPE),
        finalize_scope=env.get("INVOICES_MCP_SCOPE_FINALIZE", DEFAULT_FINALIZE_SCOPE),
        artifact_read_scope=env.get("INVOICES_MCP_SCOPE_ARTIFACT_READ", DEFAULT_ARTIFACT_READ_SCOPE),
    )


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise MCPConfigurationError(f"{key} is required for the invoices MCP service.")
    return value


def _parse_optional_tokens(value: str) -> tuple[str, ...]:
    tokens = tuple(token.strip() for token in value.split(",") if token.strip())
    return tokens


def _normalize_endpoint_path(path: str) -> str:
    normalized = "/" + path.strip("/") + "/"
    if normalized == "//":
        raise MCPConfigurationError("INVOICES_MCP_ENDPOINT_PATH must not be empty.")
    return normalized


def _parse_int(env: Mapping[str, str], key: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
    raw_value = env.get(key)
    if raw_value in (None, ""):
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise MCPConfigurationError(f"{key} must be an integer.") from exc
    if value < minimum or (maximum is not None and value > maximum):
        raise MCPConfigurationError(f"{key} must be between {minimum} and {maximum}.")
    return value


def _parse_float(env: Mapping[str, str], key: str, default: float, *, minimum: float) -> float:
    raw_value = env.get(key)
    if raw_value in (None, ""):
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise MCPConfigurationError(f"{key} must be a number.") from exc
    if value < minimum:
        raise MCPConfigurationError(f"{key} must be at least {minimum}.")
    return value
