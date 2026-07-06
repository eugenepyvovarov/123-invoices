from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MCPServiceError(Exception):
    code: str
    message: str
    status_code: int = 500
    field_errors: dict[str, Any] | None = None
    next_action: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.field_errors:
            payload["field_errors"] = self.field_errors
        if self.next_action:
            payload["next_action"] = self.next_action
        return payload


class MCPConfigurationError(MCPServiceError):
    def __init__(self, message: str):
        super().__init__(
            code="mcp_configuration_error",
            message=message,
            status_code=500,
            next_action="Check MCP service environment variables and restart the service.",
        )


@dataclass(slots=True)
class UpstreamAPIError(MCPServiceError):
    upstream_status_code: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


def map_upstream_status(status_code: int, payload: Any | None = None) -> UpstreamAPIError:
    body = payload if isinstance(payload, dict) else {}
    field_errors = body.get("field_errors") or body.get("errors")
    message = body.get("message") or body.get("detail") if isinstance(body, dict) else None

    mapping = {
        400: ("upstream_validation_error", message or "The invoices API rejected the request."),
        401: ("upstream_authentication_failed", "The MCP service could not authenticate to the invoices API."),
        403: ("upstream_permission_denied", "The invoices API denied this operation."),
        404: ("upstream_not_found", "The requested invoices API resource was not found."),
        409: ("upstream_conflict", message or "The invoices API reported a conflicting state."),
    }
    code, default_message = mapping.get(
        status_code,
        ("upstream_api_error", "The invoices API could not complete the request."),
    )
    return UpstreamAPIError(
        code=code,
        message=message or default_message,
        status_code=502 if status_code >= 500 else status_code,
        field_errors=field_errors if isinstance(field_errors, dict) else None,
        next_action="Review the request inputs or retry after the upstream invoices API is healthy.",
        upstream_status_code=status_code,
        details={"upstream_status_code": status_code},
    )
