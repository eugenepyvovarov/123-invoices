# Invoices MCP Server

The invoices MCP server exposes invoice automation tools over MCP Streamable
HTTP. It runs as the `mcp` Compose service and proxies the authenticated
invoices API; MCP tool handlers must not read Django models, database files, or
media paths directly.

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

## Environment Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `INVOICES_MCP_API_BASE_URL` | Upstream invoices API base URL used by the MCP service. In Compose this is usually `http://web:8000/api/`. | required, Compose supplies `http://web:8000/api/` |
| `INVOICES_MCP_API_TOKEN` | Dedicated invoices API bearer token for MCP-to-API calls. | required |
| `INVOICES_MCP_CLIENT_TOKENS` | Comma-separated inbound bearer token(s) accepted from approved MCP clients. | required |
| `INVOICES_MCP_HOST` | Bind host for the MCP ASGI server. | `127.0.0.1`; Compose sets `0.0.0.0` |
| `INVOICES_MCP_PORT` | Bind port. | `8765` |
| `INVOICES_MCP_ENDPOINT_PATH` | Streamable HTTP endpoint path. | `/mcp/` |
| `INVOICES_MCP_PUBLIC_URL` | Operator-facing HTTPS URL to paste into client configs. | unset |
| `INVOICES_MCP_TIMEOUT_SECONDS` | Upstream API request timeout. | `10` |
| `INVOICES_MCP_MAX_ARTIFACT_BYTES` | Maximum PDF/artifact content bytes returned by MCP artifact tools. | `5242880` |

Keep all token values in runtime secret storage or the deployment `.env`; never
commit real API tokens, MCP client tokens, client config files containing tokens,
or copied Authorization headers.

## Authentication Boundaries

The service uses two independent bearer-token boundaries:

1. **Inbound MCP client token**: AI clients call the MCP endpoint with
   `Authorization: Bearer <client-token>`. Configure one or more values in
   `INVOICES_MCP_CLIENT_TOKENS`.
2. **Upstream invoices API token**: the MCP service calls the Django API with
   `Authorization: Bearer <api-token>`. Configure this single value in
   `INVOICES_MCP_API_TOKEN`.

Do not reuse the upstream invoices API token as a client-facing MCP token. If
either token is exposed in logs, issue comments, screenshots, or client configs,
rotate it immediately.

## Creating the Dedicated API Token

Deploy does not create API or MCP tokens automatically. After the authenticated
API is deployed, create a dedicated minimum-permission API token for the MCP
service with the existing API token management command. Use a service user or
automation principal with only the invoice API permissions required for MCP
tools.

Example shape, using placeholder values:

```bash
COMPOSE_PROJECT_NAME=03-invoices docker compose exec web \
  python manage.py create_api_token \
  --username invoices-mcp \
  --name invoices-mcp \
  --scopes invoices:read,invoices:write,artifacts:read
```

Copy the generated token into runtime secrets as `INVOICES_MCP_API_TOKEN`.
Configure separate random client-facing token(s) in
`INVOICES_MCP_CLIENT_TOKENS`, for example one token per approved AI client.
Use the narrowest scopes supported by the token command and rotate tokens when
client access changes.

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

All examples use placeholders only. Replace the URL and token with values from
the approved deployment secret store.

### Hermes

```json
{
  "mcpServers": {
    "invoices": {
      "transport": "streamable_http",
      "url": "https://invoices.example.com/mcp/",
      "headers": {
        "Authorization": "Bearer <INVOICES_MCP_CLIENT_TOKEN>"
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

[mcp_servers.invoices.headers]
Authorization = "Bearer <INVOICES_MCP_CLIENT_TOKEN>"
```

### Generic Streamable HTTP MCP Client

```json
{
  "name": "invoices",
  "transport": "streamable_http",
  "endpoint": "https://invoices.example.com/mcp/",
  "authorization": {
    "type": "bearer",
    "token": "<INVOICES_MCP_CLIENT_TOKEN>"
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
  --token "<INVOICES_MCP_CLIENT_TOKEN>"
```

The probe should reject missing/invalid auth and list tools successfully with a
valid inbound MCP client token. Also confirm the HTTPS route reaches the same
endpoint before sharing client setup instructions.
