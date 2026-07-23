## Overview

Expose the invoices project through a network-accessible Streamable HTTP MCP server so approved AI clients can work with invoices through controlled tools instead of direct database or filesystem access.

Yes: all MCP HTTP protocol surface area, including tools/resources/prompts if added, must be served through `modelcontextprotocol/python-sdk`.

No: the MCP SDK should not own the entire OAuth system. Use the MCP SDK as the MCP resource server, and use Django as the in-app authorization server with `django-oauth-toolkit` plus a thin `mcp_oauth` layer for MCP-specific behavior.

## Problem

The earlier static inbound MCP bearer-token design is not sufficient for a remote HTTPS MCP endpoint. MCP Authorization expects OAuth discovery, Protected Resource Metadata, OAuth 2.1 authorization code + PKCE, resource/audience-bound access tokens, scope challenges, and safe client registration.

The MCP server must also preserve the DRF API as the invoice domain boundary: MCP client OAuth tokens must not be forwarded to DRF, and invoice tools must not bypass API validation or finalized-invoice safety rules.

## Proposed Outcome

- Run a stable Streamable HTTP MCP endpoint, with `/mcp/` as the default service path.
- Use the stable production `mcp` Python SDK line that supports `mcp.server.auth`; pin it explicitly below unstable/pre-release major versions unless reviewed.
- Serve all MCP tools/resources/prompts through the SDK.
- Use SDK-backed OAuth resource-server enforcement with:
  - `AuthSettings` for issuer/resource/scopes and Protected Resource Metadata behavior.
  - A project `TokenVerifier` backed by the Django authorization server or introspection endpoint.
  - Per-tool scope checks for read, draft-write, finalize, and artifact actions.
- Use `django-oauth-toolkit` as the default in-app authorization server for Ultramac.
- Add a small `mcp_oauth` Django layer for MCP-specific gaps: resource indicators/audience validation, AS metadata extensions, CIMD support, client-registration policy, and any metadata customization not covered by the SDK.
- Support client registration priority:
  1. Pre-registered clients for known clients such as Hermes.
  2. CIMD using HTTPS URL client IDs.
  3. DCR disabled by default and reserved for legacy compatibility only.
  4. Manual client information when needed.
- Keep MCP-to-DRF authentication separate through a dedicated minimum-privilege DRF API token/app credential such as `INVOICES_MCP_API_TOKEN`.
- Provide invoice tools for search, detail, reference lists, reusable line suggestions, draft mutation, guarded finalization, artifacts, and status inspection.
- Document OAuth, CIMD/pre-registration, scopes, endpoint URLs, environment variables, and Hermes/Codex/generic client setup.

## Constraints / Non-Goals

- Do not implement stdio-only MCP or legacy SSE compatibility; Streamable HTTP is the target.
- Do not keep static inbound MCP bearer tokens as the primary production remote-HTTP auth model.
- Do not use the MCP SDK demo/simple auth server as the production authorization server.
- Do not hand-roll OAuth grant/token machinery that `django-oauth-toolkit` can provide.
- Do not forward MCP OAuth access tokens to DRF.
- Do not expose broad admin credentials, raw stack traces, filesystem paths, artifact bodies, OAuth codes, refresh tokens, or API tokens to clients/logs.
- Do not make DCR the primary client-registration design.
- Do not implement a full enterprise IdP matrix, software statements, or platform attestation in this issue.
- Do not replace #161’s DRF `/api/` token UX; that remains complementary.
- Do not add a delete-invoice MCP tool.
- Do not add a standalone product catalog; `list_products` should expose reusable recent invoice order-line suggestions.
- Do not add persisted invoice status history; status inspection should derive from existing API-visible fields.

## Acceptance Criteria

### User Outcome

1. An approved MCP client can discover OAuth requirements from the HTTPS MCP endpoint.
2. A user can complete OAuth 2.1 authorization code + PKCE, or a documented confidential-client path, and receive an MCP-resource-bound access token.
3. Hermes, Codex, or a generic MCP client can connect through pre-registration or CIMD.
4. The client can discover invoice MCP tools with clear descriptions and JSON schemas.
5. The client can search invoices, retrieve details, list reference data, create/update drafts, finalize only with explicit confirmation, and retrieve PDF/artifact data through MCP tools.
6. `list_products` returns reusable invoice line suggestions and clearly does not claim to be a canonical product catalog.

### Technical Behavior

1. Unauthenticated MCP HTTP requests return `401` with an OAuth Bearer `WWW-Authenticate` challenge containing `resource_metadata` and scope guidance.
2. Protected Resource Metadata exposes the canonical MCP resource URL, authorization server URL, and supported scopes.
3. Authorization server metadata exposes authorization/token endpoints, `S256` PKCE support, supported scopes, and `client_id_metadata_document_supported: true`.
4. OAuth authorization/token requests validate redirect URI, PKCE, scope, client, and `resource`/audience.
5. The MCP SDK resource-server auth validates active access tokens through the project `TokenVerifier`.
6. Access-token validation rejects expired tokens, invalid issuer/introspection authority, invalid audience/resource, and missing scopes.
7. CIMD validates HTTPS metadata documents, exact `client_id`, redirect URIs, timeouts, size limits, caching, and SSRF/private-network protections.
8. Pre-registered clients take priority over CIMD.
9. Tool handlers call DRF only with the dedicated upstream API credential.
10. MCP-safe errors map upstream validation/auth/conflict/timeout/outage cases without secret leakage.

### Operations / Deployment

1. Docker/Compose includes an `mcp` service using the shared release image and `RUN_MIGRATIONS=0`.
2. Django web serves OAuth authorization-server endpoints and applies OAuth migrations.
3. Public HTTPS routing exposes the MCP endpoint and OAuth metadata/authorization/token URLs.
4. Runtime configuration documents MCP public resource URL, AS issuer URL, upstream API URL/token, OAuth validation settings, scopes, host/port, timeout, and artifact size limit.
5. Deploy does not auto-create production OAuth clients, client secrets, or DRF API tokens.
6. Deployment verification covers OAuth challenge/metadata, invalid token rejection, wrong-audience rejection, and authenticated tool discovery when a valid probe token/client is explicitly supplied.

### Validation

1. Tests cover MCP SDK auth wiring, tool registration, and JSON schema shape.
2. Tests cover PRM discovery, `WWW-Authenticate`, AS metadata, and scope advertisement.
3. Tests cover OAuth code + PKCE success/failure, invalid redirect URI, invalid resource, expired code, and invalid scope.
4. Tests cover CIMD success/failure, redirect mismatch, cache behavior, unsafe hosts, and pre-registration priority.
5. Tests cover expired token, invalid audience/resource, insufficient scope, valid tool call, and proof that MCP tokens are not forwarded to DRF.
6. Tests cover invoice search/detail/reference data/line suggestions/draft mutation/finalization/artifacts/status inspection.
7. `python manage.py test` and `scripts/ci.sh` pass.

## Implementation Plan

1. Update the `mcp` dependency to a stable SDK version that supports `mcp.server.auth` for Streamable HTTP resource-server auth.
2. Replace static inbound bearer middleware with SDK-backed auth using `AuthSettings` and a project `TokenVerifier`.
3. Add `django-oauth-toolkit` and a `mcp_oauth` Django app for OAuth server configuration, metadata, scopes, resource indicators, CIMD, and tests.
4. Implement authorization code + PKCE, resource/audience binding, token introspection/validation, and scope challenge behavior.
5. Implement CIMD client metadata resolution with SSRF protections and pre-registration priority.
6. Keep MCP-to-DRF calls behind the dedicated upstream API token and enforce per-tool scopes before tool execution.
7. Keep or complete API-backed invoice MCP tools through existing `/api/` endpoints, adding only small read-only API support if required for reusable line suggestions.
8. Update Compose/runtime/probe/docs for OAuth-protected Streamable HTTP MCP.

## Task List

- [x] Adopt MCP SDK resource-server auth
  - [x] Pin a stable `mcp` SDK version that supports `mcp.server.auth` and Streamable HTTP auth.
  - [x] Replace static inbound bearer middleware with SDK `AuthSettings` and a project `TokenVerifier`.
  - [x] Add per-tool scope enforcement for read, draft write, finalize, and artifact read actions.
  - [x] Add tests for SDK auth wiring, 401 challenge behavior, invalid tokens, insufficient scope, and valid tool discovery.

- [x] Add the Django OAuth authorization server
  - [x] Add `django-oauth-toolkit` and register provider settings, URLs, migrations, admin/client management, and scopes.
  - [x] Add `mcp_oauth` helpers for MCP resource indicators, AS metadata extensions, token validation/introspection shaping, and consent flow integration.
  - [x] Implement authorization code + PKCE with `S256`, exact redirect URI validation, resource validation, short-lived tokens, and confidential-client support where configured.
  - [x] Add tests for metadata, PKCE, redirect/resource validation, scope grants, token expiry, and invalid-client behavior.

- [x] Add CIMD support
  - [x] Fetch HTTPS URL client metadata with timeout, size, content-type, JSON schema, and exact `client_id` validation.
  - [x] Validate redirect URIs and display safe client identity information during consent.
  - [x] Reject localhost, private network, link-local, file URL, unsafe redirect, and oversized metadata targets.
  - [x] Advertise `client_id_metadata_document_supported: true`.
  - [x] Add tests for success, invalid metadata, redirect mismatch, caching, unsafe hosts, and pre-registration priority.

- [x] Complete API-backed invoice MCP tools
  - [x] Register invoice search/detail/reference/suggestion/draft/finalize/artifact/status tools with clear schemas.
  - [x] Implement all tool handlers through DRF API calls using the dedicated upstream credential.
  - [x] Ensure finalized-invoice mutation safety, explicit finalize confirmation, bounded pagination, artifact size limits, and safe error payloads.
  - [x] Add tests for success paths, upstream auth failures, validation failures, finalized safety, artifact limits, suggestions, and derived status inspection.

- [ ] Wire runtime, probes, and docs
  - [ ] Update Compose/Docker/runtime command support for the OAuth-protected MCP service.
  - [ ] Update deploy/verify/CI/runtime smoke helpers for OAuth challenge, metadata, token rejection, and authenticated tool discovery when a valid probe credential is available.
  - [ ] Document OAuth/CIMD/pre-registration setup, scopes, env vars, HTTPS URLs, upstream API credential setup, and Hermes/Codex/generic MCP client examples.
  - [ ] Update README, docs index, deployment docs, and placeholder-only environment examples.

## Deployment / Rollout

- Roll out only after the authenticated DRF API dependency from #142 is available.
- Apply `django-oauth-toolkit`/`mcp_oauth` migrations through the `web` service before starting `mcp`.
- Use Django web as the default Ultramac authorization server.
- Expose MCP and OAuth metadata/authorization/token endpoints only through approved HTTPS routes.
- Create the dedicated minimum-privilege DRF API credential after deploy; do not use broad admin credentials.
- Pre-register known clients when available; rely on CIMD for open clients with valid HTTPS metadata.
- Keep DCR disabled unless a specific legacy client requires it and the fallback is reviewed separately.
- Verify OAuth discovery, AS metadata, invalid/expired/wrong-audience rejection, and valid-token tool discovery when an explicit probe token/client is available.
- Rotate OAuth signing keys, client secrets, DRF API tokens, and refresh tokens if exposed.

## File-Level Changes

### Add

- `mcp_oauth/` Django app for OAuth metadata, resource indicators, CIMD, token validation helpers, consent support, and tests.
- `mcp_oauth/migrations/` if project-owned OAuth/CIMD persistence is needed.
- `invoices_mcp/oauth.py` or equivalent SDK `TokenVerifier` and scope helper module.
- OAuth-aware MCP probe tests/helpers.
- OAuth consent templates only where `django-oauth-toolkit` defaults need invoices-specific safe client/scope display.
- `docs/mcp-server.md` or updated MCP documentation.

### Modify

- `requirements.txt` — update `mcp` pin and add `django-oauth-toolkit` plus narrowly required JWT/crypto dependencies.
- `app/settings.py` and `app/urls.py` — register OAuth provider, `mcp_oauth`, OAuth URLs, metadata URLs, and login-exempt metadata/token behavior.
- `accounts/middleware.py` or login-exempt configuration as needed so OAuth protocol endpoints return protocol responses instead of browser redirects.
- `invoices_mcp/config.py`, `invoices_mcp/auth.py`, `invoices_mcp/server.py`, `invoices_mcp/api_client.py`, `invoices_mcp/tools.py`, `invoices_mcp/schemas.py`, and `invoices_mcp/errors.py`.
- `docker-compose.yml`, `Dockerfile`, `scripts/deploy.sh`, `scripts/verify_deploy.sh`, `scripts/runtime_smoke.sh`, and `scripts/ci.sh`.
- `README.md`, `docs/README.md`, and `docs/deployment.md`.
- API serializers/views/URLs only if reusable invoice order-line suggestions need additive read-only API support.

### Keep

- Existing browser invoice UI and PDF rendering behavior except minimal OAuth authorization/consent screens.
- Existing DRF `/api/` token model and #161 user settings token UX as separate concerns.
- Generated media/runtime files, databases, auth state, and secrets out of git.
- Managed workflow files unless MCP runtime verification explicitly requires automation integration changes.

## Open Questions

None.
