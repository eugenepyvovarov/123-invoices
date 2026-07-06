## Overview

Add a network-accessible HTTP MCP server for the invoices project so approved AI clients can search, inspect, draft, update, finalize, and retrieve invoice artifacts through controlled tools.

Current main now includes the #142 authenticated DRF API under `/api/`, account-bound bearer tokens, invoice draft create/update, `finalize`, `generate-pdf`, `download-pdf`, reference data endpoints, payments/payment applications, and API documentation. This issue should build on that API instead of reimplementing API/auth behavior or importing Django models directly.

Recommended architecture: add a separate Python MCP ASGI service in the same repository, image, and Compose stack. Default to MCP Streamable HTTP on service-local `/mcp/`.

## Problem

AI tools should not need direct database, Django model, browser session, or filesystem access to work with invoices. Current main solves the base REST API and token-auth layer, but it does not expose an MCP-compatible tool surface, inbound MCP client authentication, MCP-friendly schemas/errors, or deployment wiring for approved AI clients.

Current main also intentionally has no standalone `Product` model/catalog and no persisted invoice status-history model, so those parts of the MCP surface need to be scoped against the existing API contract rather than invented inside the MCP layer.

## Proposed Outcome

- Add an authenticated HTTP MCP service with stable tool discovery and JSON schemas.
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
  - the approved product-equivalent listing behavior
  - `create_draft_invoice`
  - `update_draft_invoice`
  - `finalize_invoice`
  - `generate_invoice_pdf`
  - `get_invoice_artifact`
  - `inspect_invoice_status_history`
- Map tools to current main API endpoints wherever possible, especially `/api/me/`, `/api/issuers/`, `/api/bank-accounts/`, `/api/customers/`, `/api/projects/`, `/api/invoices/`, `/api/invoices/{id}/finalize/`, `/api/invoices/{id}/generate-pdf/`, `/api/invoices/{id}/download-pdf/`, and `/api/payment-applications/?invoice=...`.
- Normalize upstream API failures into AI-friendly MCP errors with stable `code`, `message`, optional `field_errors`, and safe next-action guidance.
- Return invoice artifacts only through API-approved download flows, never by exposing media paths or upstream API credentials.
- Add Docker/Compose, rollout, verification, runtime smoke, and documentation support for the MCP service.

## Constraints / Non-Goals

- The #142 API dependency is satisfied on current main; do not recreate its token model, API routing, or DRF serializers unless an approved gap remains.
- Do not ship stdio-only MCP.
- Do not import Django models or read invoice/media files directly from MCP tool handlers.
- Do not expose broad admin credentials, upstream API tokens, raw stack traces, filesystem paths, or local secrets to MCP clients.
- Do not add a delete-invoice MCP tool in this issue.
- Do not silently mutate finalized invoices; use the existing API finalization action and finalized-invoice protections.
- Do not add a standalone product/catalog model solely for MCP unless the product-listing open question is answered that way.
- Do not add a persisted invoice status-history/audit model unless the status-history open question is answered that way.
- Do not add UI changes, Demo Media, or Visual Validation for this code/API/deployment task.
- Assumption: the service-local MCP path is `/mcp/`, while the operator-facing HTTPS URL is documented through configuration so it can be routed under the existing host or a separate host without code changes.

## Acceptance Criteria

### User Outcome

1. An approved AI client can connect to a stable HTTPS MCP endpoint with bearer authentication.
2. The client can discover invoice MCP tools with clear names, descriptions, and JSON schemas.
3. The client can search invoices, retrieve invoice details, and list issuer/customer/project/bank-account reference data through API-backed tools.
4. The client can create and update draft invoices without bypassing invoice validation, totals, issuer scoping, or finalized-invoice safety rules.
5. The client can explicitly request invoice finalization only through a guarded tool flow.
6. The client can retrieve invoice PDF artifact metadata and content through MCP without receiving filesystem paths or invoices API credentials.

### Technical Behavior

1. MCP tool handlers call the current main DRF API through a shared HTTP client using `Authorization: Bearer <dedicated-api-token>`.
2. MCP requests require configured inbound bearer-token authentication before tool execution.
3. Tool schemas constrain pagination, search filters, invoice IDs, reference IDs, draft payloads, line items, artifact mode, and finalization confirmation inputs.
4. Search/list tools enforce bounded pagination compatible with the API’s `page_size` limits.
5. Draft create/update tools call `/api/invoices/` and preserve API-side domain validation.
6. `update_draft_invoice` returns a safe actionable error when the API rejects finalized/non-draft mutation.
7. `finalize_invoice` requires an explicit confirmation input and calls `/api/invoices/{id}/finalize/`.
8. Artifact retrieval calls API-approved PDF generation/download endpoints and returns MCP-safe metadata/content with a configured maximum artifact size.
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
4. Tests cover invoice search/detail, reference data, draft create/update, finalization confirmation, finalized-invoice rejection, artifact retrieval, and status inspection behavior.
5. Tests cover upstream validation errors, API auth failures, not found, conflicts, timeouts, and upstream outage behavior.
6. Runtime smoke or CI coverage starts the MCP service with safe test tokens and verifies authenticated protocol reachability.

## Implementation Plan

1. Rebase implementation on current main and treat `docs/api.md` plus the current `/api/` routes as the source API contract.
2. Resolve the open product-listing, status-history, and transport compatibility questions before implementing those specific branches of the tool surface.
3. Add an `invoices_mcp` package with configuration loading, inbound auth, API client, tool definitions, schemas, error normalization, logging redaction, and ASGI/server startup.
4. Implement MCP tools by proxying the current DRF API; add API endpoints only when an approved tool cannot be safely implemented through the current API.
5. Add artifact handling that fetches PDFs through the API and returns MCP-safe metadata/content subject to configured size limits.
6. Wire the MCP service into dependencies, Docker, Compose, deploy, verify, and runtime smoke scripts.
7. Document token setup, environment variables, endpoint URL shape, reverse-proxy expectations, and Hermes/Codex/generic HTTP MCP client examples.

## Task List

- [ ] Add the MCP HTTP service foundation
  - [ ] Add MCP runtime dependencies, HTTP client dependency, and ASGI runner support.
  - [ ] Add `invoices_mcp` configuration loading for upstream API URL/token, inbound client token(s), bind host/port, endpoint path, timeout, public URL, and artifact size limit.
  - [ ] Add inbound bearer-token authentication with constant-time comparison and safe missing-configuration failures.
  - [ ] Add a shared API client wrapper with bearer-token forwarding, timeouts, response parsing, binary download support, and error mapping.
  - [ ] Add MCP server startup and Streamable HTTP endpoint wiring.
  - [ ] Add tests for config validation, auth handling, API client behavior, startup wiring, and redaction.

- [ ] Implement the API-backed invoice MCP tools
  - [ ] Add tool schemas and registration for invoice search/detail, reference data, draft mutation, finalization, artifacts, and status inspection.
  - [ ] Implement search/detail/reference tools against current `/api/` list and retrieve endpoints with bounded pagination.
  - [ ] Implement draft create/update tools against `/api/invoices/` without direct model access.
  - [ ] Implement guarded finalization against `/api/invoices/{id}/finalize/`.
  - [ ] Implement PDF generation/download artifact handling through `/generate-pdf/` and `/download-pdf/`.
  - [ ] Add tests for successful tool calls, validation failures, auth failures, finalized-invoice safety, artifact limits, and status inspection.

- [ ] Wire runtime and deployment support
  - [ ] Add the `mcp` service to Compose with shared image/env/mount conventions and `RUN_MIGRATIONS=0`.
  - [ ] Update Docker/runtime command support for launching the MCP server.
  - [ ] Update deploy and verification scripts to include the MCP service and authenticated MCP probe.
  - [ ] Update CI/runtime smoke coverage to start the MCP service with safe test tokens.
  - [ ] Add a repo-owned MCP probe helper to avoid duplicating protocol checks.

- [ ] Document MCP operation and client setup
  - [ ] Add MCP server documentation covering environment variables, token boundaries, endpoint URL, artifact limits, and operational checks.
  - [ ] Document creating the dedicated invoices API token through the existing `issue_api_token` command.
  - [ ] Add placeholder-only Hermes, Codex, and generic HTTP MCP client examples.
  - [ ] Update README/docs index/deployment docs to reference the MCP service.
  - [ ] Add placeholder-only MCP keys to `env.example`.

## Deployment / Rollout

- Roll out only from current main or later, where the authenticated DRF API and `accounts.ApiToken` migration are present.
- No MCP-specific database migration is expected unless an approved product/status-history API gap requires one.
- Add `mcp` to the Compose stack using the same image and `.env` source as `web` and `scheduler`.
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
- `env.example` — add placeholder-only MCP environment keys.
- `api/` serializers/views/URLs only if an open-question answer approves a product-equivalent or status-history endpoint not supported by the current API.

### Keep

- Existing Django browser UI, templates, static assets, and active-company session behavior.
- Existing invoice PDF rendering behavior except through API-approved MCP artifact retrieval.
- Existing `/api/` token model and endpoint contracts unless an approved gap requires a small additive API endpoint.
- Existing generated media/runtime files, databases, auth state, and secrets out of git.
- Managed workflow files unless MCP runtime verification explicitly requires an automation integration change.

## Open Questions

- Should the MCP product-listing capability expose recent reusable invoice order-line suggestions from the existing API, or should product listing be omitted until a real product catalog exists?
- Should `inspect_invoice_status_history` add a new persisted invoice status-history/audit API, or should it return current status, timestamps, PDF state, totals, and payment application activity from the existing API?
- Do Hermes, Codex, or any other required MCP clients need legacy SSE compatibility in addition to current Streamable HTTP?
