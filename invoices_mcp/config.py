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


@dataclass(frozen=True, slots=True)
class MCPConfig:
    api_base_url: str
    api_token: str
    client_tokens: tuple[str, ...]
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    endpoint_path: str = DEFAULT_ENDPOINT_PATH
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    public_url: str | None = None
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES

    @property
    def normalized_api_base_url(self) -> str:
        return self.api_base_url.rstrip("/") + "/"

    def api_url(self, path: str) -> str:
        return urljoin(self.normalized_api_base_url, path.lstrip("/"))


def load_config(env: Mapping[str, str] | None = None) -> MCPConfig:
    env = environ if env is None else env
    api_base_url = _required(env, "INVOICES_MCP_API_BASE_URL")
    api_token = _required(env, "INVOICES_MCP_API_TOKEN")
    client_tokens = _parse_tokens(_required(env, "INVOICES_MCP_CLIENT_TOKENS"))
    endpoint_path = _normalize_endpoint_path(env.get("INVOICES_MCP_ENDPOINT_PATH", DEFAULT_ENDPOINT_PATH))

    return MCPConfig(
        api_base_url=api_base_url,
        api_token=api_token,
        client_tokens=client_tokens,
        host=env.get("INVOICES_MCP_HOST", DEFAULT_HOST),
        port=_parse_int(env, "INVOICES_MCP_PORT", DEFAULT_PORT, minimum=1, maximum=65535),
        endpoint_path=endpoint_path,
        timeout_seconds=_parse_float(env, "INVOICES_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=0.1),
        public_url=env.get("INVOICES_MCP_PUBLIC_URL") or None,
        max_artifact_bytes=_parse_int(env, "INVOICES_MCP_MAX_ARTIFACT_BYTES", DEFAULT_MAX_ARTIFACT_BYTES, minimum=1),
    )


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise MCPConfigurationError(f"{key} is required for the invoices MCP service.")
    return value


def _parse_tokens(value: str) -> tuple[str, ...]:
    tokens = tuple(token.strip() for token in value.split(",") if token.strip())
    if not tokens:
        raise MCPConfigurationError("INVOICES_MCP_CLIENT_TOKENS must contain at least one token.")
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
