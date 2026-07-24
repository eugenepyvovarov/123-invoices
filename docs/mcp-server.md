# Invoices MCP Server

The invoices MCP server exposes invoice automation tools over MCP Streamable
HTTP. The MCP HTTP surface is served by the `modelcontextprotocol/python-sdk`,
runs as the `mcp` Compose service, and proxies the authenticated invoices API;
MCP tool handlers must not read Django models, database files, or media paths
directly.

## Endpoint and Transport

- Container service: `mcp`.
- Internal endpoint: `http://mcp:8765/mcp/` by default.
- Service-local path: `INVOICES_MCP_ENDPOINT_PATH`, default `/mcp/`.
- Public endpoint: set `INVOICES_MCP_PUBLIC_URL` to the approved HTTPS URL,
  for example `https://invoices.example.com/mcp/` or a dedicated MCP host.
- Transport: Streamable HTTP only. Do not configure legacy SSE or stdio-only
  clients for this deployment.

Expose the service only through the approved HTTPS reverse-proxy route. Direct
container access should remain host/internal-network scoped where possible.

Authenticated users can also find the deployment-specific MCP resource URL in
**User settings** at `/accounts/user-settings/` under **Integrations → MCP**.
That tab shows the web-side MCP configuration status, copyable endpoint, public
OAuth discovery URLs, and short client setup guidance. Keep
`INVOICES_MCP_PUBLIC_URL`, `MCP_OAUTH_RESOURCE_URL`, and
`MCP_OAUTH_ISSUER_URL` aligned so the settings page and the MCP service
advertise the same public HTTPS routes.

## Environment Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `INVOICES_MCP_API_BASE_URL` | Upstream invoices API base URL used by the MCP service. In Compose this is usually `http://web:8000/api/`. | required, Compose supplies `http://web:8000/api/` |
| `INVOICES_MCP_API_TOKEN` | Dedicated invoices API bearer token for MCP-to-API calls. | required |
| `INVOICES_MCP_OAUTH_ISSUER_URL` | OAuth issuer URL used by the SDK resource server. | required |
| `INVOICES_MCP_OAUTH_RESOURCE_URL` | Canonical MCP resource/audience URL, usually the public `/mcp/` HTTPS URL. | `INVOICES_MCP_PUBLIC_URL` fallback, otherwise required |
| `INVOICES_MCP_OAUTH_INTROSPECTION_URL` | Token introspection endpoint used by the MCP resource server. | optional; set to the in-app `/oauth/introspect/` URL |
| `INVOICES_MCP_SCOPE_READ` | Scope required for read/reference/status tools. | `invoices:mcp:read` |
| `INVOICES_MCP_SCOPE_DRAFT_WRITE` | Scope required for draft create/update tools. | `invoices:mcp:draft:write` |
| `INVOICES_MCP_SCOPE_FINALIZE` | Scope required for finalize. | `invoices:mcp:finalize` |
| `INVOICES_MCP_SCOPE_ARTIFACT_READ` | Scope required for artifact/PDF tools. | `invoices:mcp:artifact:read` |
| `INVOICES_MCP_HOST` | Bind host for the MCP ASGI server. | `127.0.0.1`; Compose sets `0.0.0.0` |
| `INVOICES_MCP_PORT` | Bind port. | `8765` |
| `INVOICES_MCP_ENDPOINT_PATH` | Streamable HTTP endpoint path. | `/mcp/` |
| `INVOICES_MCP_PUBLIC_URL` | Operator-facing HTTPS URL to paste into client configs. | unset |
| `INVOICES_MCP_TIMEOUT_SECONDS` | Upstream API request timeout. | `10` |
| `INVOICES_MCP_MAX_ARTIFACT_BYTES` | Maximum PDF/artifact content bytes returned by MCP artifact tools. | `5242880` |
| `INVOICES_MCP_AUTH_TEST_TOKENS` | Comma-separated test-only probe tokens accepted by the resource server. | unset |
| `INVOICES_MCP_WRONG_AUDIENCE_TEST_TOKEN` | Optional probe token expected to be rejected for wrong audience. | unset |

The Django web service also needs the authorization-server settings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `MCP_OAUTH_ISSUER_URL` | Public issuer URL for the in-app authorization server. | `http://localhost:8000` |
| `MCP_OAUTH_RESOURCE_URL` | Public MCP resource URL/audience issued into access tokens. | `http://localhost:8765/mcp/` |
| `MCP_OAUTH_ACCESS_TOKEN_EXPIRE_SECONDS` | MCP access-token lifetime. | `3600` |
| `MCP_OAUTH_CIMD_ENABLED` | Enable CIMD client registration. | `true` |
| `MCP_OAUTH_CIMD_TIMEOUT_SECONDS` | CIMD document fetch timeout. | `3` |
| `MCP_OAUTH_CIMD_MAX_BYTES` | Maximum CIMD document size. | `32768` |
| `MCP_OAUTH_CIMD_CACHE_SECONDS` | CIMD metadata cache TTL. | `3600` |
| `MCP_OAUTH_INTROSPECTION_TOKEN` | Optional shared secret required by `/oauth/introspect/`. | unset |

Keep all token/client-secret values in runtime secret storage or the deployment
`.env`; never commit real API tokens, OAuth access/refresh tokens, client
secrets, client config files containing tokens, or copied Authorization headers.

## OAuth and Authentication Boundaries

The service uses two independent auth boundaries:

1. **Inbound MCP OAuth**: remote clients discover OAuth requirements from a
   `401` Bearer challenge with `resource_metadata=...`, complete OAuth 2.1
   authorization code + PKCE or a documented confidential-client flow, and call
   `/mcp/` with an MCP-resource-bound access token.
2. **Upstream invoices API token**: the MCP service calls the Django API with
   `Authorization: Bearer <api-token>`. Configure this single value in
   `INVOICES_MCP_API_TOKEN`.

The MCP OAuth access token is validated by the MCP SDK resource server and must
not be forwarded to DRF. The MCP service uses only `INVOICES_MCP_API_TOKEN` for
DRF calls. Do not reuse the upstream invoices API token as a client-facing OAuth
token or client secret. If any token is exposed in logs, issue comments,
screenshots, or client configs, rotate it immediately.

The default Ultramac authorization server is the Django web service using
`django-oauth-toolkit` plus the project `mcp_oauth` helpers. Public metadata
URLs are:

- Protected Resource Metadata: `https://invoices.example.com/.well-known/oauth-protected-resource`
- Authorization Server Metadata: `https://invoices.example.com/.well-known/oauth-authorization-server`
- Authorization endpoint: `https://invoices.example.com/o/authorize/`
- Token endpoint: `https://invoices.example.com/o/token/`
- Introspection endpoint: `https://invoices.example.com/oauth/introspect/`

External IdPs such as Keycloak/Auth0 are a future integration option, but the
default deployment for this issue is the in-app Django authorization server.
The same non-secret metadata links and supported scopes are summarized for
end-users in **User settings → Integrations → MCP** so client setup does not
require reading this operator document.

## Client Registration

Use this priority order:

1. **Pre-register known clients** such as Hermes in the Django OAuth
   applications admin. Use confidential clients only when the client can protect
   a secret; otherwise use a public authorization-code client with PKCE.
2. **CIMD** for open clients with no prior relationship. The client ID is an
   HTTPS URL serving a JSON client metadata document. The server advertises
   `client_id_metadata_document_supported: true`, fetches documents with size
   and timeout limits, rejects unsafe/private-network locations, validates exact
   `client_id`, and allows only declared redirect URIs.
3. **DCR** is not the primary design and remains disabled/deferred unless a
   legacy client explicitly needs it.
4. Manual client information may be entered by an operator when needed.

When publishing a first-party client metadata document, host it over HTTPS and
include only placeholder-safe public metadata such as `client_id`,
`client_name`, `redirect_uris`, `grant_types`, `response_types`, and allowed
scopes. Do not publish secrets in CIMD documents.

## Creating the Dedicated API Token

Deploy does not create API tokens, OAuth clients, or client secrets
minimum-permission API token for the MCP service with the existing API token
management command. Use a service user or automation principal with only the
invoice API permissions required for MCP tools.

Example shape, using placeholder values:

```bash
COMPOSE_PROJECT_NAME=03-invoices docker compose exec web \
  python manage.py create_api_token \
  --username invoices-mcp \
  --name invoices-mcp \
  --scopes invoices:read,invoices:write,artifacts:read
```

Copy the generated token into runtime secrets as `INVOICES_MCP_API_TOKEN`.
Use the narrowest scopes supported by the token command and rotate the token
when MCP service access changes. Separately, pre-register OAuth clients or use
CIMD for inbound MCP users; do not give clients the DRF API token.

## Scopes

The in-app authorization server advertises these least-privilege scopes:

- `invoices:mcp:read` — search/detail/reference/list_products/status tools.
- `invoices:mcp:draft:write` — create/update draft invoice tools.
- `invoices:mcp:finalize` — finalize draft invoice tool.
- `invoices:mcp:artifact:read` — PDF/artifact generation and retrieval tools.

Grant only the scopes a client needs. Finalization should be reserved for
trusted clients and still requires explicit `confirm=true` at tool-call time.

## Tools and Safety

The MCP service exposes tools for invoice search/detail, issuer/customer/project
and bank-account lists, reusable recent order-line suggestions, draft invoice
create/update, guarded finalization, PDF generation/artifact retrieval, and
status inspection.

Important safety behavior:

- `list_products` returns reusable recent invoice order-line suggestions, not a
  canonical product catalog.
- Draft create/update requests are sent to the API so domain validation, totals,
  issuer scoping, and finalized-invoice rules remain centralized.
- `finalize_invoice` requires explicit `confirm=true` and may be irreversible.
- Artifact tools call API-approved PDF endpoints and enforce
  `INVOICES_MCP_MAX_ARTIFACT_BYTES`; clients should request metadata first and
  fetch content only when needed.
- Error payloads are normalized for AI clients and should not include upstream
  tokens, raw stack traces, filesystem paths, or artifact bodies.

## Client Examples

All examples use placeholders only. Replace URLs/client IDs with approved
deployment values. Users can copy the deployment's endpoint from **User settings
→ Integrations → MCP**. OAuth clients should start from the MCP endpoint, follow the
`WWW-Authenticate` challenge to Protected Resource Metadata, discover the AS
metadata, then complete authorization code + PKCE. Pre-registered clients use
their assigned `client_id`; CIMD clients use their HTTPS metadata URL as
`client_id`.

### Hermes

```json
{
  "mcpServers": {
    "invoices": {
      "transport": "streamable_http",
      "url": "https://invoices.example.com/mcp/",
      "auth": {
        "type": "oauth2_pkce",
        "client_id": "https://client.example.com/hermes/client-metadata.json",
        "scopes": ["invoices:mcp:read", "invoices:mcp:draft:write"]
      }
    }
  }
}
```

### Codex

```toml
[mcp_servers.invoices]
transport = "streamable_http"
url = "https://invoices.example.com/mcp/"
auth = "oauth2_pkce"
client_id = "codex-invoices-pre-registered-client-id"
scopes = ["invoices:mcp:read", "invoices:mcp:artifact:read"]
```

### Generic Streamable HTTP MCP Client

```json
{
  "name": "invoices",
  "transport": "streamable_http",
  "endpoint": "https://invoices.example.com/mcp/",
  "authorization": {
    "type": "oauth2_authorization_code_pkce",
    "resource": "https://invoices.example.com/mcp/",
    "client_id": "https://client.example.com/invoices-mcp-client.json",
    "scope": "invoices:mcp:read invoices:mcp:draft:write"
  }
}
```

## Operational Checks

Verify the running service after deploy:

```bash
COMPOSE_PROJECT_NAME=03-invoices docker compose ps web scheduler mcp
COMPOSE_PROJECT_NAME=03-invoices docker compose logs --no-color --tail 50 mcp
COMPOSE_PROJECT_NAME=03-invoices docker compose exec -T mcp \
  python scripts/mcp_probe.py \
  --url http://127.0.0.1:8765/mcp/ \
  --token "<OPTIONAL_VALID_MCP_ACCESS_TOKEN>"
```

The probe always checks the OAuth challenge, Protected Resource Metadata, and
invalid-token rejection. When `--token` is provided, it also lists tools through
the SDK client. Add `--wrong-audience-token` when an explicit wrong-resource
probe credential is available. Also confirm the HTTPS route reaches the same
endpoint before sharing client setup instructions.
