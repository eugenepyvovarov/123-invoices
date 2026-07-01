## Overview

Add a network-accessible HTTP MCP server for the invoices project so approved AI clients can discover invoice automation tools, search and inspect invoices, create/update drafts, retrieve artifacts, and request guarded finalization through the authenticated DRF API from #142.

Recommended architecture: implement a separate Python ASGI MCP service in the same repository/image/Compose stack. The MCP service must call the authenticated invoices API over HTTP and must not import Django models or read invoice files directly except for a clearly documented architectural exception.

Assumption: target the current MCP Streamable HTTP transport at a stable `/mcp/` endpoint, not a stdio-only server.

## Problem

AI tools currently need direct database/filesystem knowledge or manual browser/API work to inspect and manage invoice data. That is unsafe because it bypasses invoice domain rules, active issuer scoping, draft/finalized safety, artifact access controls, and audit-friendly API validation.

The repository also does not currently contain a product catalog model or invoice status-history model, so the MCP tool surface must be tied to the #142 API contract rather than inventing new direct model behavior inside the MCP layer.

## Proposed Outcome

- Add an authenticated HTTP MCP service with discoverable tools and stable JSON schemas.
- Use a dedicated upstream API bearer token with minimum permissions for all invoices API calls.
- Require separate inbound authentication for approved MCP clients before tool execution.
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
- Normalize API and validation failures into AI-friendly errors with `code`, `message`, `field_errors`, and safe next-action guidance.
- Guard irreversible or high-risk operations with draft-only checks, explicit confirmation inputs, and API-side permission/rule enforcement.
- Add deployment, runtime verification, and documentation for the MCP endpoint, tokens, environment variables, and Hermes/Codex/other HTTP MCP client configuration.

## Constraints / Non-Goals

- Depends on #142; implement after the authenticated DRF API exists.
- Do not bypass the DRF API by importing Django models in MCP tool handlers.
- Do not expose broad admin credentials to MCP clients.
- Do not return upstream API tokens, filesystem paths, raw stack traces, or secrets in MCP responses.
- Do not add a delete-invoice tool in this issue.
- Do not silently mutate finalized invoices; draft update tools must reject non-draft invoices unless the API exposes a safe, explicit action.
- Do not invent a new `Product` model solely for MCP unless the product/catalog contract is confirmed.
- Do not add UI changes, demo media, or visual validation for this code/API-only work.

## Acceptance Criteria

### User Outcome

1. An approved AI client can connect to a stable HTTPS MCP endpoint and discover invoice tools with clear schemas.
2. An AI client can search invoices and retrieve invoice detail through the DRF API-backed MCP tools.
3. An AI client can list issuer/customer/project reference data needed to create draft invoices.
4. An AI client can create and update draft invoices without bypassing invoice validation or issuer scoping.
5. An AI client can request invoice artifact retrieval without receiving direct filesystem access or privileged API credentials.
6. Finalization is available only through an explicit guarded tool flow when the invoices API allows it.

### Technical Behavior

1. MCP tool handlers use a shared API client that sends `Authorization: Bearer <dedicated-api-token>` to the #142 API.
2. MCP client requests require their own configured bearer token or equivalent approved-client gate before tool execution.
3. Tool input schemas constrain pagination, filters, invoice IDs, draft payloads, line items, artifact identifiers, and confirmation flags.
4. Draft creation/update tools call API endpoints that enforce invoice domain rules, totals, issuer/customer/project scoping, and validation.
5. `update_draft_invoice` refuses finalized/non-draft invoices by default and returns an actionable safe error.
6. `finalize_invoice` requires an explicit confirmation input and calls a dedicated API finalization/status action rather than patching status blindly.
7. Artifact retrieval returns API-approved artifact metadata and content/URL handling without local file reads by the MCP server.
8. Upstream 400/401/403/404/409/5xx responses are mapped to stable MCP errors suitable for AI clients.
9. Timeouts, connection failures, and configuration errors fail closed with no secret leakage.

### Operations / Deployment

1. Docker/Compose includes an `mcp` service or equivalent runtime entrypoint using the same release image.
2. The MCP service can reach the web/API service internally and can be exposed externally only through the approved HTTPS route.
3. Runtime configuration is documented, including upstream API base URL, upstream API token, inbound MCP client token, bind host/port, endpoint path, and timeout settings.
4. Deployment verification includes an MCP health/protocol probe in addition to the existing web and scheduler checks.
5. Documentation includes example HTTP MCP client configurations for Hermes, Codex, and a generic client using placeholders only.

### Validation

1. Tests cover tool registration and JSON schema shape.
2. Tests cover upstream API request construction, bearer-token forwarding, pagination/filter mapping, and response normalization.
3. Tests cover inbound MCP auth failure, upstream API auth failure, validation failure, not-found, conflict, and upstream outage behavior.
4. Tests cover draft-only update protection and finalized-invoice safety rules.
5. Tests cover artifact retrieval behavior without filesystem access.
6. Docker/runtime smoke validation starts the MCP service and verifies it is reachable with configured auth.

## Implementation Plan

1. Confirm or extend the #142 DRF API endpoints needed for search, detail, references, draft create/update, finalization, artifacts, and status/history; keep MCP access API-only.
2. Add an `invoices_mcp` package with configuration loading, inbound auth middleware, API client, tool definitions, schemas, and error normalization.
3. Implement the MCP HTTP server using the chosen Python MCP SDK and ASGI runner.
4. Add a dedicated Compose service/command for the MCP server, internal API base URL configuration, and deployment verification probes.
5. Add focused unit/integration tests using mocked upstream API responses and, where practical, Django test API endpoints from #142.
6. Update documentation and environment examples with safe placeholders and client setup examples.

## Task List

- [ ] Add the MCP server package
  - [ ] Add configuration loading for upstream API URL/token, inbound client token, bind host/port, endpoint path, and request timeout.
  - [ ] Add inbound bearer-token authentication for MCP HTTP requests.
  - [ ] Add a typed API client wrapper using `httpx` or equivalent with timeout, auth header, and error mapping.
  - [ ] Add MCP server startup/ASGI entrypoint using the selected MCP SDK.
  - [ ] Add tests for config validation, auth handling, startup wiring, and safe configuration errors.

- [ ] Implement invoice MCP tools
  - [ ] Add search/detail/reference-data tools that proxy the DRF API with bounded pagination and stable schemas.
  - [ ] Add draft create/update tools that validate payload shape and call API endpoints rather than models.
  - [ ] Add guarded finalization behavior with explicit confirmation and safe rejection when API/domain rules disallow it.
  - [ ] Add artifact retrieval/status-history tools using only API-exposed endpoints.
  - [ ] Add tests for tool schemas, successful API calls, validation failures, auth failures, safety refusals, and artifact handling.

- [ ] Wire runtime and deployment support
  - [ ] Add MCP runtime dependencies to `requirements.txt`.
  - [ ] Add Docker/Compose command or service wiring for the MCP HTTP server.
  - [ ] Update runtime smoke and deploy verification scripts to include an authenticated MCP health/protocol probe.
  - [ ] Add tests for script-level runtime checks where existing script coverage patterns support it.

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
- Expose the MCP service through the approved HTTPS route and keep direct container ports restricted to the deployment host or internal network where possible.
- Create a dedicated minimum-permission API token for invoice automation and configure it as a runtime secret; rotate it if exposed.
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
- `docs/mcp-server.md`

### Modify

- `requirements.txt` — add MCP SDK, HTTP client, and ASGI runtime dependencies.
- `Dockerfile` — ensure runtime image includes MCP dependencies and entrypoint support.
- `docker-compose.yml` — add or wire the MCP service.
- `scripts/ci.sh`, `scripts/runtime_smoke.sh`, and `scripts/verify_deploy.sh` — include MCP runtime/protocol checks.
- `README.md`, `docs/development.md`, `docs/deployment.md`, and `docs/README.md` — document setup, validation, deployment, and client configuration.
- `env.example` — add placeholder-only MCP environment keys if this remains the repo’s environment reference.
- #142 API files, only if required endpoints/actions are missing and this issue is approved to close those API gaps before MCP wiring.

### Keep

- Existing Django UI behavior and templates.
- Existing invoice PDF generation behavior except through API-exposed artifact actions.
- Existing web and scheduler services.
- Managed workflow files unless runtime verification explicitly requires a managed automation change.
- Local/runtime secrets, tokens, databases, media files, and generated artifacts out of git.

## Open Questions

- Should the live MCP endpoint be exposed on the existing invoices host under `/mcp/`, or on a separate hostname such as `mcp.<domain>`?
- Should `list_products` use a product/catalog endpoint from #142, or should it expose existing reusable/recent invoice line items because the current repository has no `Product` model?
- Should this issue add an invoice status/history API when #142 does not already provide one, or should the MCP history tool only return current status, timestamps, payment applications, and artifact metadata?
- What should `finalize_invoice` do contractually: call a dedicated draft-to-invoiced finalization API that locks finalized invoice edits, or only request the existing status change when the API allows it?
