## Overview

Add a network-accessible MCP server for the invoices project so approved AI clients can search, inspect, draft, update, finalize, and retrieve invoice artifacts through controlled tools.

This issue should build on the #142 authenticated DRF API rather than importing Django models or reading files directly. Recommended architecture: add a separate Python ASGI MCP service in the same repository, image, and Compose stack, using MCP Streamable HTTP on a service-local `/mcp/` endpoint.

## Problem

AI tools should not need direct database, Django model, browser session, or filesystem access to work with invoices. The authenticated API provides the correct domain and permission boundary, but the project still needs an MCP-compatible tool surface, inbound MCP client authentication, AI-friendly schemas/errors, and deployment wiring for approved HTTPS clients.

The project does not currently have a standalone product catalog or persisted invoice status-history model. For this issue, product-style listing should expose reusable invoice order-line suggestions, and status/history inspection should be derived from existing invoice, PDF, totals, timestamp, and payment-application data.

## Proposed Outcome

- Add an authenticated Streamable HTTP MCP service with stable tool discovery and JSON schemas.
- Use two separate auth boundaries:
  - inbound MCP client bearer token(s) for approved AI clients;
  - a dedicated minimum-permission invoices API bearer token for MCP-to-DRF calls.
- Implement API-backed tools for:
  - `search_invoices`
  - `get_invoice`
  - `list_issuers`
  - `list_bank_accounts`
  - `list_customers`
  - `list_projects`
  - `list_products`, described as reusable recent invoice order-line suggestions rather than a true catalog
  - `create_draft_invoice`
  - `update_draft_invoice`
  - `finalize_invoice`
  - `generate_invoice_pdf`
  - `get_invoice_artifact`
  - `inspect_invoice_status_history`
- Implement `inspect_invoice_status_history` as an API-derived status summary/activity view, not a new persisted audit/history model.
- Normalize upstream API failures into MCP-safe errors with stable `code`, `message`, optional `field_errors`, and safe next-action guidance.
- Return invoice artifacts only through API-approved download flows, never by exposing media paths or upstream API credentials.
- Add Docker/Compose, rollout, verification, runtime smoke, and documentation support for the MCP service.

## Constraints / Non-Goals

- Do not ship stdio-only MCP.
- Do not add legacy SSE compatibility; only Streamable HTTP is required.
- Do not import Django models or read invoice/media files directly from MCP tool handlers.
- Do not expose broad admin credentials, upstream API tokens, raw stack traces, filesystem paths, or local secrets to MCP clients.
- Do not add a delete-invoice MCP tool in this issue.
- Do not silently mutate finalized invoices; use API-side domain rules and guarded MCP inputs.
- Do not add a standalone product/catalog model for MCP.
- Do not add a persisted invoice status-history/audit model in this issue.
- Do not add UI changes, Demo Media, or Visual Validation for this code/API/deployment task.
- Assumption: the service-local MCP path is `/mcp/`, while the public HTTPS URL is documented through configuration so operators can route it under the existing host or a separate host without code changes.

## Acceptance Criteria

### User Outcome

1. An approved AI client can connect to a stable HTTPS MCP endpoint with bearer authentication.
2. The client can discover invoice MCP tools with clear names, descriptions, and JSON schemas.
3. The client can search invoices, retrieve invoice details, and list issuer/customer/project/bank-account reference data through API-backed tools.
4. The product-listing tool returns reusable recent invoice order-line suggestions and clearly does not claim to be a canonical product catalog.
5. The client can create and update draft invoices without bypassing invoice validation, totals, issuer scoping, or finalized-invoice safety rules.
6. The client can explicitly request invoice finalization only through a guarded tool flow.
7. The client can retrieve invoice PDF/artifact metadata and content through MCP without receiving filesystem paths or invoices API credentials.
8. The client can inspect invoice status using current status, timestamps, PDF state, totals, and payment-application activity.

### Technical Behavior

1. MCP tool handlers call the DRF API through a shared HTTP client using `Authorization: Bearer <dedicated-api-token>`.
2. MCP requests require configured inbound bearer-token authentication before tool execution.
3. Tool schemas constrain pagination, search filters, invoice IDs, reference IDs, draft payloads, line items, artifact mode, and finalization confirmation inputs.
4. Search/list tools enforce bounded pagination compatible with the API’s page-size limits.
5. Draft create/update tools call API endpoints and preserve API-side domain validation.
6. `update_draft_invoice` returns a safe actionable error when the API rejects finalized or non-draft mutation.
7. `finalize_invoice` requires explicit confirmation input and calls the API finalization action.
8. Artifact retrieval calls API-approved PDF generation/download endpoints and respects a configured maximum artifact size.
9. Upstream 400/401/403/404/409/5xx, timeouts, connection failures, and invalid configuration map to stable MCP errors without secret leakage.
10. Logs redact inbound tokens, upstream tokens, authorization headers, and artifact bodies.

### Operations / Deployment

1. Docker/Compose includes an `mcp` service using the same release image as `web` and `scheduler`.
2. The MCP service runs with `RUN_MIGRATIONS=0` and depends on the web/API service for upstream API access.
3. Deployment scripts pull, recreate, and verify `web`, `scheduler`, and `mcp` as one release.
4. Runtime configuration is documented with placeholders for upstream API base URL, upstream API token, inbound MCP tokens, bind host/port, endpoint path, public URL, timeout, and artifact size limit.
5. No API or MCP tokens are created automatically during deploy.
6. Deployment verification confirms the MCP service is running, rejects missing/invalid auth, and accepts the configured client token for a protocol/tool-list probe.

### Validation

1. Tests cover MCP tool registration and JSON schema shape.
2. Tests cover inbound MCP auth success/failure and constant-time token comparison behavior.
3. Tests cover upstream API request construction, bearer-token forwarding, pagination/filter mapping, and response normalization.
4. Tests cover invoice search/detail, reference data, reusable line suggestions, draft create/update, finalization confirmation, finalized-invoice rejection, artifact retrieval, and status inspection.
5. Tests cover upstream validation errors, API auth failures, not found, conflicts, timeouts, and upstream outage behavior.
6. Runtime smoke or CI coverage starts the MCP service with safe test tokens and verifies authenticated protocol reachability.

## Implementation Plan

1. Rebase implementation on the #142 API and treat the current `/api/` routes/docs as the source contract.
2. Add an `invoices_mcp` package with configuration loading, inbound auth, API client, tool definitions, schemas, error normalization, logging redaction, and ASGI/server startup.
3. Implement Streamable HTTP only; do not add SSE or stdio-specific deployment paths.
4. Implement MCP tools by proxying the DRF API; add a small additive read-only API endpoint only if reusable invoice order-line suggestions are not already exposed by the API.
5. Implement status inspection from existing invoice/API fields and payment-application activity rather than adding an audit table.
6. Add artifact handling that fetches PDFs/artifacts through the API and returns MCP-safe metadata/content subject to configured size limits.
7. Wire the MCP service into dependencies, Docker, Compose, deploy, verify, and runtime smoke scripts.
8. Document token setup, environment variables, endpoint URL shape, reverse-proxy expectations, and Hermes/Codex/generic Streamable HTTP MCP client examples.

## Task List

- [ ] Add the MCP HTTP service foundation
  - [ ] Add MCP runtime dependencies, HTTP client dependency, and ASGI runner support.
  - [ ] Add `invoices_mcp` configuration for upstream API URL/token, inbound client token(s), bind host/port, endpoint path, timeout, public URL, and artifact size limit.
  - [ ] Add inbound bearer-token authentication with constant-time comparison and safe missing-configuration failures.
  - [ ] Add a shared API client wrapper with bearer-token forwarding, timeouts, response parsing, binary download support, and error mapping.
  - [ ] Add MCP server startup and Streamable HTTP endpoint wiring.
  - [ ] Add tests for config validation, auth handling, API client behavior, startup wiring, and redaction.

- [ ] Implement the API-backed invoice MCP tools
  - [ ] Add tool schemas and registration for invoice search/detail, reference data, reusable line suggestions, draft mutation, finalization, artifacts, and status inspection.
  - [ ] Implement search/detail/reference tools against current `/api/` list and retrieve endpoints with bounded pagination.
  - [ ] Implement `list_products` as reusable recent invoice order-line suggestions, adding a read-only API endpoint only if the API does not already expose that data.
  - [ ] Implement draft create/update tools against invoice API endpoints without direct model access.
  - [ ] Implement guarded finalization against the API finalization action.
  - [ ] Implement PDF/artifact handling through API-approved generation/download endpoints.
  - [ ] Implement status inspection as a derived API summary using current invoice state, timestamps, PDF state, totals, and payment-application activity.
  - [ ] Add tests for successful tool calls, validation failures, auth failures, finalized-invoice safety, artifact limits, reusable suggestion behavior, and status inspection.

- [ ] Wire runtime and deployment support
  - [ ] Add the `mcp` service to Compose with shared image/env/mount conventions and `RUN_MIGRATIONS=0`.
  - [ ] Update Docker/runtime command support for launching the MCP server.
  - [ ] Update deploy and verification scripts to include the MCP service and authenticated MCP probe.
  - [ ] Update CI/runtime smoke coverage to start the MCP service with safe test tokens.
  - [ ] Add a repo-owned MCP probe helper to avoid duplicating protocol checks.

- [ ] Document MCP operation and client setup
  - [ ] Add MCP server documentation covering environment variables, token boundaries, endpoint URL, artifact limits, Streamable HTTP transport, and operational checks.
  - [ ] Document creating the dedicated invoices API token through the existing token management command.
  - [ ] Add placeholder-only Hermes, Codex, and generic Streamable HTTP MCP client examples.
  - [ ] Update README/docs index/deployment docs to reference the MCP service.
  - [ ] Add placeholder-only MCP keys to the committed environment example.

## Deployment / Rollout

- Roll out only after the authenticated DRF API dependency from #142 is present.
- No MCP-specific database migration is expected.
- Add `mcp` to the Compose stack using the same image and runtime env source as `web` and `scheduler`.
- Configure `INVOICES_MCP_API_BASE_URL` to the internal web/API service, for example `http://web:8000/api/`.
- Configure the MCP service with `RUN_MIGRATIONS=0`; keep migrations owned by the `web` startup path.
- Create a dedicated minimum-permission invoices API token after deploy using the existing management command; store it as a runtime secret.
- Configure separate inbound MCP client token(s); do not reuse the upstream invoices API token as a client-facing credential.
- Expose the MCP service only through the approved HTTPS route and keep direct container ports restricted to the host/internal network where possible.
- Update rollout verification to check `web`, `scheduler`, and `mcp`, plus authenticated and unauthenticated MCP probe behavior.
- Rotate upstream or inbound tokens if they are exposed in logs, client configs, or issue comments.

## File-Level Changes

### Add

- `invoices_mcp/__init__.py`
- `invoices_mcp/config.py`
- `invoices_mcp/server.py`
- `invoices_mcp/auth.py`
- `invoices_mcp/api_client.py`
- `invoices_mcp/tools.py`
- `invoices_mcp/schemas.py`
- `invoices_mcp/errors.py`
- `tests/test_mcp_*.py`
- `scripts/mcp_probe.py` or equivalent repo-owned protocol probe helper
- `docs/mcp-server.md`

### Modify

- `requirements.txt` — add MCP SDK, HTTP client, and ASGI/runtime dependencies.
- `Dockerfile` — ensure runtime image supports the MCP server command.
- `docker-compose.yml` — add the `mcp` service.
- `scripts/deploy.sh` — include `mcp` in pull/recreate rollout.
- `scripts/verify_deploy.sh` — verify the `mcp` container and authenticated MCP probe.
- `scripts/runtime_smoke.sh` and `scripts/ci.sh` — include MCP runtime/protocol smoke coverage.
- `README.md`, `docs/README.md`, and `docs/deployment.md` — document the MCP server and rollout shape.
- Committed environment example — add placeholder-only MCP environment keys.
- API serializers/views/URLs from the #142 API only if reusable invoice order-line suggestions need a small additive read-only endpoint.

### Keep

- Existing Django browser UI, templates, static assets, and active-company session behavior.
- Existing invoice PDF rendering behavior except through API-approved MCP artifact retrieval.
- Existing `/api/` token model and endpoint contracts unless the reusable suggestion endpoint is missing.
- Existing generated media/runtime files, databases, auth state, and secrets out of git.
- Managed workflow files unless MCP runtime verification explicitly requires an automation integration change.

## Open Questions

None.
