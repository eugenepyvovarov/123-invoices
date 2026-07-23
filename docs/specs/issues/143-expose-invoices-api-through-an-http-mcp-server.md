## Overview

Add a network-accessible MCP server for the invoices project so approved AI clients can search, inspect, draft, update, finalize, and retrieve invoice artifacts through controlled tools.

This issue should build on #142’s authenticated DRF API. MCP tool handlers should call the API, not import Django models or read invoice/media files directly.

Inbound HTTP MCP authentication should use OAuth 2.1 for Streamable HTTP, not static MCP bearer tokens. Recommended Ultramac default: implement an in-app Django authorization server so the project can support OAuth discovery, code + PKCE, MCP-bound access tokens, pre-registered clients, and Client ID Metadata Documents (CIMD) without depending on an external IdP feature gap.

## Problem

AI tools should not need direct database, Django model, browser session, or filesystem access to work with invoices. The DRF API provides the domain boundary, but remote MCP access also needs a protocol-compatible authorization boundary.

Static inbound MCP bearer tokens are not sufficient for a network-accessible MCP endpoint because they do not provide OAuth discovery, user authorization, client registration priority, scope challenges, or resource/audience-bound tokens. The MCP server must also avoid token passthrough: MCP client access tokens must not be forwarded to the invoices DRF API.

## Proposed Outcome

- Add a Streamable HTTP MCP service with a stable `/mcp/` endpoint and discoverable invoice tools.
- Replace inbound static MCP bearer authentication with OAuth 2.1 protected-resource behavior:
  - unauthenticated MCP requests return `401` with `WWW-Authenticate: Bearer resource_metadata="..."` and appropriate scope guidance;
  - the MCP resource serves OAuth 2.0 Protected Resource Metadata;
  - inbound access tokens are validated for issuer, expiry, scope, and MCP resource/audience.
- Add an in-app Django OAuth authorization server as the default Ultramac deployment choice:
  - authorization code + PKCE for public clients;
  - documented confidential-client path for trusted automation where needed;
  - RFC 8414/OIDC-style authorization server metadata;
  - `client_id_metadata_document_supported: true` for CIMD-capable clients.
- Support client registration in this priority order:
  1. pre-registered clients for known clients such as Hermes when configured;
  2. CIMD using HTTPS URL client IDs;
  3. DCR only as a disabled/backwards-compatibility fallback if a legacy client requires it;
  4. manual client entry.
- Keep MCP-to-DRF authentication separate through a dedicated minimum-privilege API token or app credential. The MCP service must never forward the user’s MCP OAuth access token to DRF.
- Enforce least-privilege MCP scopes, initially:
  - `invoices:read` for search/detail/reference/status reads;
  - `invoices:draft:write` for draft create/update;
  - `invoices:finalize` for guarded finalization;
  - `invoices:artifacts:read` for artifact metadata/content retrieval.
- Implement API-backed MCP tools for invoice search/detail, issuer/customer/project/bank-account lists, reusable order-line suggestions, draft mutation, finalization, PDF/artifact retrieval, and status inspection.
- Document OAuth, CIMD/pre-registration setup, endpoint URLs, environment variables, and Hermes/Codex/generic client configuration.

## Constraints / Non-Goals

- Do not ship stdio-only MCP or legacy SSE compatibility; HTTP Streamable MCP is the target.
- Do not accept static inbound MCP bearer tokens as production remote-HTTP authorization.
- Do not forward MCP OAuth access tokens to the DRF API.
- Do not expose broad admin credentials, upstream API tokens, raw stack traces, filesystem paths, or local secrets to MCP clients.
- Do not make DCR the primary design; keep it deferred or disabled unless a legacy client explicitly requires it.
- Do not implement a full enterprise IdP matrix, software statements, or platform attestation in this issue.
- Do not replace #161’s DRF `/api/` token UX; DRF API tokens remain complementary and separate from MCP OAuth.
- Do not add a delete-invoice MCP tool.
- Do not add a standalone product/catalog model; `list_products` should expose reusable recent invoice order-line suggestions.
- Do not add a persisted invoice status-history/audit model; status inspection should derive from existing API-visible invoice, PDF, totals, timestamp, and payment-application data.
- Assumption: the service-local MCP path is `/mcp/`, while the public HTTPS resource URL is configurable for same-host or dedicated-host routing.

## Acceptance Criteria

### User Outcome

1. An approved MCP client can discover OAuth requirements from the HTTPS MCP endpoint without pre-shared static bearer-token instructions.
2. A user can complete OAuth 2.1 authorization code + PKCE, or a documented trusted confidential-client path, and receive an access token bound to the MCP resource.
3. Hermes, Codex, or a generic MCP client can connect through pre-registration or CIMD-based client metadata.
4. The client can discover invoice MCP tools with clear names, descriptions, and JSON schemas.
5. The client can search invoices, retrieve invoice details, and list issuer/customer/project/bank-account reference data through API-backed tools.
6. The product-listing tool returns reusable recent invoice order-line suggestions and clearly does not claim to be a canonical catalog.
7. The client can create/update draft invoices, explicitly finalize allowed invoices, and retrieve invoice artifacts without bypassing invoice domain rules.
8. The client can inspect invoice status using current status, timestamps, PDF state, totals, and payment-application activity.

### Technical Behavior

1. Unauthenticated MCP requests return `401` with a standards-compatible `WWW-Authenticate` Bearer challenge containing `resource_metadata`.
2. Protected Resource Metadata includes the MCP resource identifier, authorization server URL(s), and supported scopes.
3. Authorization server metadata includes authorization/token endpoints, supported code challenge methods including `S256`, supported scopes, and `client_id_metadata_document_supported: true`.
4. OAuth authorization requests require `resource` targeting the canonical MCP resource and reject mismatched redirect URIs, unsupported clients, missing PKCE, or invalid scopes.
5. CIMD support fetches HTTPS client metadata documents, validates exact `client_id` match, validates redirect URIs, applies timeouts/size limits, and blocks private-network/SSRF targets.
6. Pre-registered client configuration takes precedence over CIMD when both are available.
7. Access-token validation rejects expired tokens, invalid issuer tokens, invalid audience/resource tokens, and tokens missing required scopes.
8. Insufficient tool scope returns `403` with an OAuth Bearer `insufficient_scope` challenge and required scope guidance.
9. MCP tool handlers call the DRF API through a shared HTTP client using only the dedicated upstream API credential.
10. MCP logs and errors redact inbound tokens, upstream API tokens, authorization headers, OAuth codes, refresh tokens, and artifact bodies.
11. Upstream API failures, validation errors, conflicts, timeouts, and outages map to stable MCP-safe errors without secret leakage.

### Operations / Deployment

1. Docker/Compose includes an `mcp` service using the same release image as `web` and `scheduler`.
2. OAuth authorization-server endpoints run with the Django web service and are available over approved HTTPS URLs.
3. Deployment applies any OAuth migrations through the web service; the MCP service runs with `RUN_MIGRATIONS=0`.
4. Runtime configuration documents the MCP public resource URL, AS issuer URL, PRM URL, upstream API URL/token, OAuth signing or introspection settings, scopes, bind host/port, timeout, and artifact size limit.
5. No production OAuth clients, API tokens, or client secrets are automatically created by deploy.
6. Known clients can be pre-registered by an operator, while CIMD is enabled for open clients that publish valid HTTPS metadata.
7. Deployment verification confirms OAuth challenge/metadata behavior, rejects invalid/expired/wrong-audience tokens, and accepts a valid MCP-bound token for tool discovery.

### Validation

1. Tests cover MCP tool registration and JSON schema shape.
2. Tests cover Protected Resource Metadata, `WWW-Authenticate` challenge shape, authorization-server metadata, and scope advertisement.
3. Tests cover OAuth code + PKCE success and failure cases, including missing PKCE, invalid redirect URI, invalid resource, expired authorization code, and invalid scope.
4. Tests cover CIMD success, invalid metadata, redirect mismatch, unavailable metadata, metadata caching, and SSRF/private-network rejection.
5. Tests cover token validation for invalid audience/resource, expired token, invalid issuer, insufficient scope, and successful tool call with a valid token.
6. Tests prove the MCP service does not forward the MCP client access token to DRF.
7. Tests cover upstream API request construction, bearer-token forwarding for the dedicated API credential, pagination/filter mapping, and response normalization.
8. Tests cover invoice search/detail, reference data, reusable line suggestions, draft create/update, finalization confirmation, finalized-invoice rejection, artifact retrieval, and status inspection.
9. `python manage.py test` and `scripts/ci.sh` pass.

## Implementation Plan

1. Rebase on the #142 DRF API contract and treat `/api/` as the source of invoice domain rules.
2. Add an in-app OAuth authorization-server layer for MCP with code + PKCE, scopes, client records, grants/tokens, metadata, and optional trusted confidential-client support.
3. Add CIMD support to the authorization server, including safe metadata fetching, validation, caching, and SSRF protections.
4. Add Protected Resource Metadata and OAuth Bearer challenge handling to the MCP HTTP service.
5. Replace static inbound MCP bearer middleware with OAuth resource-server validation that enforces issuer, expiry, audience/resource, and tool scopes.
6. Keep MCP-to-DRF calls behind a dedicated minimum-privilege API token/app credential and ensure inbound MCP tokens are never forwarded upstream.
7. Implement invoice MCP tools by proxying DRF endpoints, with additive read-only API support only if reusable order-line suggestions are missing.
8. Update deployment scripts, runtime smoke/probe helpers, docs, and tests for OAuth-protected Streamable HTTP MCP.

## Task List

- [ ] Add the in-app MCP OAuth authorization server
  - [ ] Add OAuth server dependencies, models/migrations, settings, and URL routes for clients, grants, tokens, scopes, and resource indicators.
  - [ ] Implement authorization, token, metadata, and token validation/introspection support using existing Django login/OTP sessions.
  - [ ] Enforce authorization code + PKCE with `S256`, exact redirect URI validation, `resource` validation, short-lived access tokens, and refresh-token safety where supported.
  - [ ] Add pre-registered client management through admin or management commands.
  - [ ] Add focused tests for metadata, PKCE, redirect/resource validation, scope grants, token expiry, and confidential-client behavior.

- [ ] Add CIMD client registration support
  - [ ] Implement HTTPS URL `client_id` metadata fetching with timeout, size, content-type, JSON shape, exact `client_id`, and redirect URI validation.
  - [ ] Add SSRF protections that reject localhost, private networks, link-local, file URLs, redirects to unsafe targets, and oversized responses.
  - [ ] Advertise `client_id_metadata_document_supported: true` in authorization-server metadata.
  - [ ] Ensure pre-registered clients take priority over CIMD and leave DCR disabled unless explicitly configured for legacy compatibility.
  - [ ] Add tests for CIMD success, failure, caching, redirect mismatch, unsafe hosts, and pre-registration priority.

- [ ] Replace inbound MCP auth with OAuth resource-server enforcement
  - [ ] Add Protected Resource Metadata routes for the MCP resource, including path-specific and root well-known behavior as appropriate.
  - [ ] Return OAuth Bearer `WWW-Authenticate` challenges for missing/invalid auth and insufficient-scope responses for tool-level scope failures.
  - [ ] Validate inbound access tokens for issuer, expiry, resource/audience, active status, and scopes before MCP tool execution.
  - [ ] Remove production reliance on `INVOICES_MCP_CLIENT_TOKENS`; keep any test-only bypass unavailable to remote production HTTP.
  - [ ] Add tests for 401/PRM discovery, invalid audience, expired token, insufficient scope, valid token tool discovery, and redaction.

- [ ] Implement the API-backed invoice MCP tools
  - [ ] Add tool schemas and registration for invoice search/detail, reference lists, reusable line suggestions, draft mutation, finalization, artifacts, and status inspection.
  - [ ] Implement search/detail/reference tools against current `/api/` list and retrieve endpoints with bounded pagination.
  - [ ] Implement `list_products` as reusable recent invoice order-line suggestions, adding a small read-only API endpoint only if needed.
  - [ ] Implement draft create/update, guarded finalization, PDF generation/artifact retrieval, and derived status inspection through DRF API calls only.
  - [ ] Enforce per-tool scope requirements and safe validation/error payloads.
  - [ ] Add tests for successful tool calls, validation failures, upstream auth failures, finalized-invoice safety, artifact limits, suggestion behavior, and status inspection.

- [ ] Wire runtime, probes, and documentation
  - [ ] Add the `mcp` service to Compose with shared image/env/mount conventions and `RUN_MIGRATIONS=0`.
  - [ ] Update Docker/runtime command support for launching the MCP server.
  - [ ] Update deploy, verify, CI, and runtime smoke helpers to check OAuth challenge/metadata and authenticated tool discovery.
  - [ ] Add or update a repo-owned MCP probe helper that can validate PRM discovery and a configured valid MCP-bound token.
  - [ ] Document OAuth/CIMD/pre-registration setup, scopes, environment variables, HTTPS endpoint URLs, upstream API credential setup, and Hermes/Codex/generic client examples.
  - [ ] Update README/docs index/deployment docs and committed placeholder environment examples.

## Deployment / Rollout

- Roll out only after the authenticated DRF API dependency from #142 is present.
- Apply OAuth-related migrations through the `web` service before starting the `mcp` service.
- Configure the Django web service as the default Ultramac authorization server and expose its OAuth metadata/authorization/token endpoints over HTTPS.
- Configure the MCP service with the canonical public MCP resource URL, PRM URL, AS issuer URL, upstream API base URL, dedicated upstream API credential, bind host/port, timeout, and artifact size limit.
- Create a dedicated minimum-privilege DRF API token or app credential for MCP-to-DRF calls after deploy; do not use broad admin credentials.
- Pre-register known clients when available; rely on CIMD for open clients that publish valid HTTPS metadata.
- Keep DCR disabled unless a specific legacy client requires it and the fallback is reviewed separately.
- Expose the MCP service only through the approved HTTPS route; keep direct container ports internal.
- Verify missing auth produces the OAuth challenge, PRM and AS metadata are reachable, invalid/expired/wrong-audience tokens are rejected, and a valid MCP-bound token can list tools.
- Rotate OAuth signing keys, client secrets, upstream API tokens, or refresh tokens if exposed in logs, issue comments, screenshots, or client configs.

## File-Level Changes

### Add

- `mcp_oauth/` Django app for OAuth clients, grants/tokens, metadata, CIMD, and tests.
- `mcp_oauth/migrations/` for OAuth server persistence.
- `mcp_oauth/templates/` only for minimal authorization/consent screens required by the OAuth flow.
- `invoices_mcp/oauth.py` or equivalent resource-server token validation module.
- `invoices_mcp/protected_resource.py` or equivalent Protected Resource Metadata/challenge helpers.
- `tests/test_mcp_oauth_*.py` and/or app-level OAuth tests.
- `scripts/mcp_probe.py` updates or a dedicated OAuth-aware probe helper.
- `docs/mcp-server.md`.

### Modify

- `requirements.txt` — add OAuth/JWT/crypto dependencies as needed.
- `app/settings.py` and `app/urls.py` — register OAuth app, metadata routes, and login-exempt behavior where appropriate.
- `invoices_mcp/config.py`, `invoices_mcp/auth.py`, `invoices_mcp/server.py`, `invoices_mcp/api_client.py`, `invoices_mcp/tools.py`, `invoices_mcp/schemas.py`, and `invoices_mcp/errors.py`.
- `docker-compose.yml`, `Dockerfile`, `scripts/deploy.sh`, `scripts/verify_deploy.sh`, `scripts/runtime_smoke.sh`, and `scripts/ci.sh`.
- `README.md`, `docs/README.md`, and `docs/deployment.md`.
- Committed environment example with placeholder-only OAuth/MCP keys.
- API serializers/views/URLs only if reusable invoice order-line suggestions need a small additive read-only endpoint.

### Keep

- Existing Django browser invoice UI, active-company behavior, and PDF rendering behavior except for minimal OAuth authorization screens.
- Existing `/api/` token model and #161 user settings REST API token UX as separate DRF concerns.
- Existing generated media/runtime files, databases, auth state, and secrets out of git.
- Managed workflow files unless MCP runtime verification explicitly requires an automation integration change.

## Open Questions

None.
