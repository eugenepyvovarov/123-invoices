from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .config import MCPConfig
from .errors import MCPConfigurationError, UpstreamAPIError, map_upstream_status


class InvoicesAPIClient:
    def __init__(self, config: MCPConfig, client: httpx.AsyncClient | None = None):
        if not config.api_token:
            raise MCPConfigurationError("INVOICES_MCP_API_TOKEN is required for upstream API calls.")
        self.config = config
        self._client = client or httpx.AsyncClient(timeout=config.timeout_seconds)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        response = await self._request(method, path, params=params, json=json)
        if response.content in (b"", None):
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamAPIError(
                code="upstream_invalid_response",
                message="The invoices API returned a non-JSON response.",
                status_code=502,
                next_action="Retry after confirming the invoices API endpoint is healthy.",
            ) from exc

    async def download(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        max_bytes: int | None = None,
    ) -> tuple[bytes, Mapping[str, str]]:
        response = await self._request("GET", path, params=params)
        content = response.content
        limit = max_bytes if max_bytes is not None else self.config.max_artifact_bytes
        if len(content) > limit:
            raise UpstreamAPIError(
                code="artifact_too_large",
                message="The requested artifact exceeds the configured MCP artifact size limit.",
                status_code=413,
                next_action="Request artifact metadata or increase INVOICES_MCP_MAX_ARTIFACT_BYTES.",
            )
        return content, response.headers

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {}) or {}
        headers = {**headers, "Authorization": f"Bearer {self.config.api_token}"}
        try:
            response = await self._client.request(
                method,
                self.config.api_url(path),
                headers=headers,
                timeout=self.config.timeout_seconds,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise UpstreamAPIError(
                code="upstream_timeout",
                message="The invoices API did not respond before the MCP timeout.",
                status_code=504,
                next_action="Retry later or increase INVOICES_MCP_TIMEOUT_SECONDS.",
            ) from exc
        except httpx.RequestError as exc:
            raise UpstreamAPIError(
                code="upstream_unavailable",
                message="The invoices API is unavailable to the MCP service.",
                status_code=502,
                next_action="Check network routing and the invoices web service health.",
            ) from exc

        if response.status_code >= 400:
            raise map_upstream_status(response.status_code, _safe_json(response))
        return response


def _safe_json(response: httpx.Response) -> Any | None:
    try:
        return response.json()
    except ValueError:
        return None
