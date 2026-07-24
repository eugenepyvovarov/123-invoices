# Invoices API

The invoices API is an authenticated, account-scoped Django REST Framework API
served under `/api/`. It is intended for server-to-server tools and future MCP
integrations that need to discover connected companies, create and finalize
invoices, download artifacts, upload direct expense records, and read dashboard
report data without depending on browser session state.

Interactive schema documentation is available at `/api/docs/`; the OpenAPI JSON
schema is available at `/api/schema/`.

## Authentication and token setup

API tokens are owned by Django users. A token can access every issuer/company
linked to its owner through `Issuer.users`; superuser-owned tokens can access all
issuers. Tokens are not company-bound and do not use the browser active-company
session.

### User settings workflow

Authenticated users can manage their own REST API Bearer tokens from **User
settings** at `/accounts/user-settings/` in the **Integrations** hub. Use the
**API** tab for REST Bearer token creation, listing, and revocation. The adjacent
**MCP** tab is for OAuth-based MCP client connection guidance; it does not
create or reveal REST API tokens. The integrations hub is also separate from the
**Expense import AI provider** key, which is only used for statement-import
mapping inference and is not accepted by `/api/`.

From the **API** tab in User settings, create a token by entering a required token name and,
optionally, an expiry date/time. The plaintext token is shown once immediately
after creation in a copy-friendly field. Copy it into the calling system's secret
store before leaving the page; later visits list only metadata such as name,
prefix, created time, last-used time, expiry, and active/expired/revoked status.
Use the same section to revoke tokens you own. Revocation is a soft revoke and
the token record remains visible as revoked.

### CLI and admin escape hatches

The User settings workflow is preferred for day-to-day owner-managed tokens.
The existing management commands and Django admin remain available for operators
who need administrative escape hatches.

Issue a token with the management command:

```bash
python manage.py issue_api_token alice@example.com --name "mcp integration"
```

Optionally add an ISO-8601 expiry:

```bash
python manage.py issue_api_token alice@example.com \
  --name "short lived tool token" \
  --expires-at "2026-12-31T23:59:59+00:00"
```

The plaintext token is printed once at creation time. Store it in the calling
system's secret store. Operators can list or revoke stored token records without
revealing plaintext secrets:

```bash
python manage.py list_api_tokens
python manage.py revoke_api_token inv_live_abcd1234
```

Staff users can also inspect token metadata and revoke tokens from Django admin
through the `ApiToken` admin model. Admin and CLI views never recover plaintext
secrets after creation.

Send the token as a Bearer credential on every data request:

```bash
curl -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  https://invoices.example.com/api/me/
```

Missing, invalid, expired, or revoked credentials return JSON `401` responses;
API routes do not redirect to the browser login flow.

## Pagination, filters, search, and ordering

List endpoints are paginated with `count`, `next`, `previous`, and `results`.
Use `page` and `page_size` to navigate results.

Common query parameters:

- `issuer`: restrict to a connected issuer/company by numeric issuer ID.
- `external_id`: match the caller-provided external identifier where supported.
- `search`: search configured text fields such as names, references, memos, and
  descriptions.
- `ordering`: order by supported fields, for example `ordering=-issued_date`.

Endpoint-specific filters include:

- Customers: `issuer`, `external_id`, `is_active`.
- Projects: `issuer`, `customer`, `status`, `external_id`.
- Invoices: `issuer`, `customer`, `project`, `status`, `external_id`,
  `issued_after`, `issued_before`, `due_after`, `due_before`.
- Payments: `issuer`, `customer`, `project`, `status`, `external_id`,
  `received_after`, `received_before`.
- Payment applications: `issuer`, `payment`, `invoice`, `external_id`.
- Expenses: `issuer`, `customer`, `project`, `invoice`, `external_id`,
  `paid_after`, `paid_before`, `has_attachment`.

Example invoice list request:

```bash
curl -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  "https://invoices.example.com/api/invoices/?issuer=7&status=draft&search=ACME&ordering=-issued_date"
```

## Account and company discovery

Use `/api/me/` to discover the authenticated account and every issuer/company
available to the token:

```json
{
  "account": {"id": 12, "username": "alice", "email": "alice@example.com"},
  "issuers": [
    {
      "id": 7,
      "url": "https://invoices.example.com/api/issuers/7/",
      "company": {"id": 42, "name": "Life Is Good Labs"},
      "invoice_format": "LIG-{number}",
      "next_invoice_number": 1042,
      "bank_accounts": []
    }
  ]
}
```

Issuer and bank-account endpoints are read-only metadata and selection endpoints
for this API version:

- `GET /api/issuers/`
- `GET /api/issuers/{id}/`
- `GET /api/bank-accounts/`
- `GET /api/bank-accounts/{id}/`

## Customers and projects

Customers and projects support list, retrieve, create, update, partial update,
and delete through standard DRF routes. Writes are validated against issuers the
token owner can access.

Create a customer:

```bash
curl -X POST -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  -H "Content-Type: application/json" \
  https://invoices.example.com/api/customers/ \
  -d '{
    "external_id": "crm-1001",
    "issuer": 7,
    "company_name": "ACME Ltd",
    "billing_email": "ap@example.test",
    "is_active": true
  }'
```

Create a project for that customer:

```json
{
  "external_id": "job-2026-001",
  "customer": 55,
  "title": "Website refresh",
  "status": "active",
  "project_code": "WEB-001"
}
```

## Invoices, order lines, PDFs, and lifecycle actions

Invoices use nested `order_lines` for product/service line items. This API does
not add a separate product/service catalog. Create and update calls recalculate
invoice totals transactionally.

Create a draft invoice:

```bash
curl -X POST -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  -H "Content-Type: application/json" \
  https://invoices.example.com/api/invoices/ \
  -d '{
    "external_id": "tool-inv-1001",
    "issuer": 7,
    "customer": 55,
    "project": 81,
    "bank_account": 3,
    "issued_date": "2026-07-03",
    "due_date": "2026-08-02",
    "comment": "Created by API",
    "order_lines": [
      {
        "external_id": "line-1",
        "line_type": "service",
        "description": "Implementation work",
        "quantity": "10.00",
        "unit_price": "150.00"
      }
    ]
  }'
```

Draft invoices can be updated or deleted. Finalized invoices cannot be edited or
deleted through the API. Finalize a draft with the explicit action:

```bash
curl -X POST -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  https://invoices.example.com/api/invoices/100/finalize/
```

Generate and download the authenticated PDF artifact:

```bash
curl -X POST -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  https://invoices.example.com/api/invoices/100/generate-pdf/

curl -L -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  -o invoice-100.pdf \
  https://invoices.example.com/api/invoices/100/download-pdf/
```

Invoice responses include stable IDs, `external_id`, issuer/customer/project
metadata, money fields, `has_pdf`, `pdf_url`, timestamps, status, and nested
order lines.

## Payments and payment applications

Payments and payment applications are account-scoped and recalculate invoice
amount/status metadata when applications change.

Create a payment:

```json
{
  "external_id": "stripe-pmt-1001",
  "issuer": 7,
  "customer": 55,
  "project": 81,
  "amount": "1500.00",
  "received_at": "2026-07-15",
  "status": "received",
  "memo": "API payment"
}
```

Apply it to an invoice:

```json
{
  "external_id": "stripe-pmt-1001-inv-100",
  "payment": 44,
  "invoice": 100,
  "amount_applied": "1500.00"
}
```

## Reports

Dashboard-style report data is available at `/api/reports/dashboard/`. It can
run across all accessible issuers or be filtered to one or more issuer IDs.

```bash
curl -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  "https://invoices.example.com/api/reports/dashboard/?issuer=7&issuer=8"
```

The response includes:

- `issuer_ids`: issuer IDs included in the report.
- `totals`: invoice, paid, due, overdue, payment, and expense totals.
- `monthly_revenue`: monthly invoice totals and counts.
- `monthly_expenses`: monthly expense totals and counts.
- `receivables`: status counts with due and overdue amounts.
- `recent_activity`: recent invoices, payments, and expenses.

## Expenses and attachments

Expense endpoints support direct expense records with optional attachments. CSV,
XLS, XLSX, and ZIP statement import workflows are not exposed through this API.

Create a JSON expense without an attachment:

```bash
curl -X POST -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  -H "Content-Type: application/json" \
  https://invoices.example.com/api/expenses/ \
  -d '{
    "external_id": "receipt-1001",
    "issuer": 7,
    "paid_date": "2026-07-01",
    "amount": "49.99",
    "description": "Domain renewal",
    "exclude_from_reports": false
  }'
```

Upload an expense with a multipart attachment:

```bash
curl -X POST -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  -F issuer=7 \
  -F paid_date=2026-07-01 \
  -F amount=49.99 \
  -F description="Domain renewal" \
  -F attachment=@receipt.pdf \
  https://invoices.example.com/api/expenses/
```

Download or remove an attachment:

```bash
curl -L -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  -o receipt.pdf \
  https://invoices.example.com/api/expenses/200/download-attachment/

curl -X PATCH -H "Authorization: Bearer $INVOICES_API_TOKEN" \
  -H "Content-Type: application/json" \
  https://invoices.example.com/api/expenses/200/ \
  -d '{"remove_attachment": true}'
```

Attachment validation follows the same extension and size rules as the existing
expense UI. Artifact endpoints stream files through authenticated views and do
not expose direct media filesystem paths.

## Error format

Errors are JSON. Common cases include:

- `401 Unauthorized`: missing, malformed, invalid, revoked, expired, or inactive
  token credentials.
- `403 Forbidden`: authenticated but not permitted.
- `404 Not Found`: object or artifact is outside the authenticated account scope
  or does not exist.
- `400 Bad Request`: validation errors such as cross-issuer relationships,
  finalized invoice mutation, unsupported attachment type, or malformed filters.

Validation responses use DRF field-error shapes, for example:

```json
{
  "customer": ["Customer must belong to the invoice issuer."]
}
```
