## Overview

Add a network-accessible HTTP MCP server for the invoices project so approved AI clients can search and inspect invoices, create/update draft invoices, retrieve invoice artifacts, and request guarded finalization through the authenticated DRF API from #142.

Recommended architecture: implement a separate Python ASGI MCP service in the same repository, release image, and Compose stack. The MCP service should use the public/internal DRF API over HTTP and must not import Django models or read invoice/media files directly.

Default recommendation: use the current MCP Streamable HTTP transport at a service-local `/mcp/` endpoint. If required clients need legacy SSE compatibility, resolve that before expanding the transport surface.

## Problem

AI tools currently need direct database/filesystem knowledge or manual browser/API work to inspect and manage invoice data. That bypasses invoice domain rules, issuer scoping, draft/finalized safety, artifact access controls, and audit-friendly API validation.

The repository also does not currently expose a product catalog model or invoice status-history model, so the MCP tool surface must be tied to the #142 API contract rather than inventing direct model behavior in the MCP layer.

## Proposed Outcome

- Add an authenticated HTTP MCP service with discoverable tools and stable JSON schemas.
- Use separate authentication boundaries:
  - inbound MCP client bearer token(s) for approved AI clients;
  - a dedicated minimum-permission upstream API bearer token for MCP-to-DRF calls.
- Provide tools for:
  - `search_invoices`
  - `get_invoice`
  - `list_issuers`
  - `list_customers`
  - `list_projects`
  - `list_products` or the approved product-equivalent API contract
  - `create_draft_invoice`
  - `update_draft_invoice`
  - `finalize_invoice`
  - `get_invoice_artifact`
  - `inspect_invoice_status_history`
- Normalize upstream API and validation failures into AI-friendly MCP errors with stable `code`, `message`, `field_errors`, and safe next-action guidance.
- Guard irreversible or high-risk operations with draft-only checks, explicit confirmation inputs, and API-side permission/domain-rule enforcement.
- Add deployment wiring, runtime probes, and documentation for the MCP endpoint, tokens, environment variables, and Hermes/Codex/generic HTTP MCP client configuration.

## Constraints / Non-Goals

- Depends on #142; implement after the authenticated DRF API and token auth are available.
- Do not recreate #142’s base API/auth work in this issue unless closing small endpoint gaps approved for the MCP tool surface.
- Do not ship a stdio-only MCP server.
- Do not bypass the DRF API by importing Django models in MCP tool handlers.
- Do not expose broad admin credentials, upstream API tokens, filesystem paths, raw stack traces, or secrets to MCP clients.
- Do not add a delete-invoice tool in this issue.
- Do not silently mutate finalized invoices; draft update tools must reject non-draft invoices unless the API exposes a safe explicit action.
- Do not invent a new `Product` model solely for MCP unless the product/catalog contract is confirmed.
- Do not read PDF/media files directly from the MCP service; retrieve artifacts only through API-approved artifact endpoints or URLs.
- Do not add UI changes, demo media, or visual validation for this code/API-only work.

## Acceptance Criteria

### User Outcome

1. An approved AI client can connect to a stable HTTPS MCP endpoint and discover invoice tools with clear schemas.
2. An AI client can search invoices and retrieve invoice detail through DRF API-backed MCP tools.
3. An AI client can list issuer/customer/project reference data needed to create draft invoices.
4. An AI client can create and update draft invoices without bypassing invoice validation, totals, issuer scoping, or project/customer rules.
5. An AI client can request invoice artifact retrieval without receiving direct filesystem access or privileged API credentials.
6. Finalization is available only through an explicit guarded tool flow when the invoices API allows it.

### Technical Behavior

1. MCP tool handlers use a shared API client that sends `Authorization: Bearer <dedicated-api-token>` to the #142 API.
2. MCP client requests require configured inbound authentication before tool execution.
3. Tool input schemas constrain pagination, filters, invoice IDs, draft payloads, line items, artifact identifiers, and confirmation flags.
4. Draft create/update tools call API endpoints that enforce invoice domain rules and validation.
5. `update_draft_invoice` refuses finalized/non-draft invoices by default and returns an actionable safe error.
6. `finalize_invoice` requires explicit confirmation and calls a dedicated API finalization/status action rather than patching status blindly.
7. Artifact retrieval returns API-approved artifact metadata, content, or URL handling without local file reads by the MCP server.
8. Upstream 400/401/403/404/409/5xx responses are mapped to stable MCP errors suitable for AI clients.
9. Timeouts, connection failures, and configuration errors fail closed with no secret leakage.
10. MCP logs redact tokens and avoid logging full artifact content.

### Operations / Deployment

1. Docker/Compose includes an `mcp` service or equivalent runtime entrypoint using the same release image.
2. The MCP service can reach the web/API service internally and is exposed externally only through the approved HTTPS route.
3. Runtime configuration is documented, including upstream API base URL, upstream API token, inbound MCP client token(s), bind host/port, endpoint path, and timeout settings.
4. Deployment rollout includes the MCP service alongside `web` and `scheduler`.
5. Deployment verification includes an authenticated MCP health/protocol probe and confirms missing/invalid auth is rejected.
6. Documentation includes placeholder-only HTTP MCP client configurations for Hermes, Codex, and a generic client.

### Validation

1. Tests cover tool registration and JSON schema shape.
2. Tests cover upstream API request construction, bearer-token forwarding, pagination/filter mapping, and response normalization.
3. Tests cover inbound MCP auth failure, upstream API auth failure, validation failure, not-found, conflict, and upstream outage behavior.
4. Tests cover draft-only update protection and finalized-invoice safety rules.
5. Tests cover artifact retrieval behavior without filesystem access.
6. Docker/runtime smoke validation starts the MCP service and verifies it is reachable with configured auth.

## Implementation Plan

1. Confirm the #142 DRF API endpoints needed for search, detail, reference data, draft create/update, finalization, artifacts, and status/history.
2. Where #142 lacks an endpoint required by the approved MCP tool surface, add the API endpoint/action and tests first; do not add direct-model MCP fallbacks.
3. Add an `invoices_mcp` package with configuration loading, inbound auth middleware, API client, tool definitions, schemas, and error normalization.
4. Implement the MCP HTTP server using the selected Python MCP SDK and ASGI runner.
5. Wire Docker/Compose, deploy, runtime smoke, and verification scripts so `web`, `scheduler`, and `mcp` roll out together.
6. Add operator/client documentation and focused unit/integration coverage for the MCP service and API interactions.

## Task List

- [ ] Close approved DRF API contract gaps
  - [ ] Map each required MCP tool to an existing #142 API endpoint/action.
  - [ ] Add missing read/reference/artifact/status endpoints only when required for the approved tool surface.
  - [ ] Add missing draft mutation or guarded finalization actions only when required for safe MCP behavior.
  - [ ] Add API tests for auth, scoping, validation, artifact access, and finalized-invoice safety.

- [ ] Add the MCP service foundation
  - [ ] Add configuration loading for upstream API URL/token, inbound client token(s), bind host/port, endpoint path, and request timeout.
  - [ ] Add inbound bearer-token authentication using constant-time token comparison.
  - [ ] Add a typed API client wrapper using `httpx` or equivalent with timeout, auth header, and error mapping.
  - [ ] Add MCP server startup/ASGI entrypoint using the selected MCP SDK.
  - [ ] Add tests for config validation, auth handling, startup wiring, and safe configuration errors.

- [ ] Implement invoice MCP tools
  - [ ] Add search/detail/reference-data tools that proxy the DRF API with bounded pagination and stable schemas.
  - [ ] Add draft create/update tools that validate payload shape and call API endpoints rather than models.
  - [ ] Add guarded finalization behavior with explicit confirmation and safe rejection when API/domain rules disallow it.
  - [ ] Add artifact retrieval and status/history tools using only API-exposed endpoints.
  - [ ] Add tests for tool schemas, successful API calls, validation failures, auth failures, safety refusals, and artifact handling.

- [ ] Wire runtime and deployment support
  - [ ] Add MCP runtime dependencies to `requirements.txt`.
  - [ ] Add Docker/Compose command or service wiring for the MCP HTTP server.
  - [ ] Update deploy and verification scripts to include the MCP service and an authenticated MCP probe.
  - [ ] Update runtime smoke/CI checks to start the MCP service with safe test tokens and verify protocol reachability.
  - [ ] Add a repo-owned MCP probe helper if needed to avoid duplicating protocol checks across scripts.

- [ ] Document operator and client setup
  - [ ] Document required environment variables and token expectations with placeholders only.
  - [ ] Document how to create/use the dedicated minimum-permission API token from the #142 API/auth flow.
  - [ ] Document the stable endpoint URL shape and reverse-proxy/HTTPS expectations.
  - [ ] Add Hermes, Codex, and generic HTTP MCP client configuration examples.
  - [ ] Update README/docs index references for the new MCP server documentation.

## Deployment / Rollout

- Roll out only after #142 is deployed and the required API endpoints/token auth are available.
- No MCP-specific database migration is expected unless missing #142 API/token capabilities require one.
- Add the MCP service to the existing Compose stack using the same image and `.env` source, with `INVOICES_MCP_API_BASE_URL` pointed at the internal web/API service.
- Configure the MCP service with `RUN_MIGRATIONS=0`; keep migrations owned by the `web` startup path.
- Expose the MCP service through the approved HTTPS route and keep direct container ports restricted to the deployment host or internal network where possible.
- Create a dedicated minimum-permission API token for invoice automation and configure it as a runtime secret; rotate it if exposed.
- Update rollout scripts so `web`, `scheduler`, and `mcp` are pulled/recreated/verified as one release.
- Post-deploy verification should confirm the web, scheduler, and MCP services are running and that the MCP endpoint rejects missing/invalid auth while accepting the configured client token.

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

- `requirements.txt` — add MCP SDK, HTTP client, and ASGI runtime dependencies.
- `Dockerfile` — ensure runtime image includes MCP dependencies and entrypoint support.
- `docker-compose.yml` — add or wire the MCP service.
- `scripts/deploy.sh` — include the MCP service in rollout.
- `scripts/ci.sh`, `scripts/runtime_smoke.sh`, and `scripts/verify_deploy.sh` — include MCP runtime/protocol checks.
- `README.md`, `docs/development.md`, `docs/deployment.md`, and `docs/README.md` — document setup, validation, deployment, and client configuration.
- `env.example` — add placeholder-only MCP environment keys.
- #142 DRF API modules under `invoices/` and URL routing only if required endpoints/actions are missing and this issue is approved to close those gaps before MCP wiring.

### Keep

- Existing Django UI behavior and templates.
- Existing invoice PDF generation behavior except through API-exposed artifact actions.
- Existing web and scheduler behavior, aside from rollout/verification adding the MCP service.
- Managed workflow files unless runtime verification explicitly requires a managed automation change.
- Local/runtime secrets, tokens, databases, media files, and generated artifacts out of git.

## Open Questions

- Should the live MCP endpoint be exposed on the existing invoices host under `/mcp/`, or on a separate hostname such as `mcp.<domain>`?
- Do Hermes, Codex, or any other required MCP clients need legacy SSE compatibility in addition to current Streamable HTTP?
- Should `list_products` use a product/catalog endpoint from #142, or should it expose existing reusable/recent invoice line items because the current repository has no `Product` model?
- Should this issue add an invoice status/history API when #142 does not already provide one, or should the MCP history tool only return current status, timestamps, payment applications, and artifact metadata?
- What should `finalize_invoice` do contractually: call a dedicated draft-to-invoiced finalization API that locks finalized invoice edits, or only request the existing status change when the API allows it?
