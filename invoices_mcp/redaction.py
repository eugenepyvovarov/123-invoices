from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "artifact_body",
    "body",
    "content",
    "api_token",
    "client_token",
    "invoices_mcp_api_token",
    "invoices_mcp_client_tokens",
    "token",
}


def redact_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    return "[REDACTED]"


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if key.lower().replace("-", "_") in SENSITIVE_KEYS:
            redacted[key] = redact_value(value)
        elif isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted
