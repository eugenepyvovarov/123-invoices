from __future__ import annotations

import hmac
from collections.abc import Iterable

from starlette.responses import JSONResponse

from .errors import MCPConfigurationError


AUTH_ERROR_PAYLOAD = {
    "code": "mcp_authentication_failed",
    "message": "A valid bearer token is required to use the invoices MCP endpoint.",
}


def extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    scheme, separator, token = authorization_header.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def token_matches(candidate: str | None, configured_tokens: Iterable[str]) -> bool:
    tokens = tuple(token for token in configured_tokens if token)
    if not tokens:
        raise MCPConfigurationError("No inbound MCP client tokens are configured.")
    if candidate is None:
        return False
    return any(hmac.compare_digest(candidate, token) for token in tokens)


def is_authorized(authorization_header: str | None, configured_tokens: Iterable[str]) -> bool:
    return token_matches(extract_bearer_token(authorization_header), configured_tokens)


class BearerAuthASGIMiddleware:
    def __init__(self, app, client_tokens: Iterable[str]):
        self.app = app
        self.client_tokens = tuple(client_tokens)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        authorization = headers.get(b"authorization")
        header_value = authorization.decode("latin1") if authorization else None
        if not is_authorized(header_value, self.client_tokens):
            response = JSONResponse(AUTH_ERROR_PAYLOAD, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
