## Overview

Add an authenticated, account-scoped Django REST Framework API under `/api/` so external tools and a future HTTP MCP server can safely work with invoices without direct database or filesystem access. The API should authenticate as a user account, expose every issuer/company connected to that account, and support invoices, customers, projects, payments, reports, invoice PDFs, and expense uploads.

## Problem

The current app is browser/session-oriented and centered on the active company in the UI session. That does not work well for server-to-server tools, AI agents, or MCP integrations that need stable JSON endpoints, token authentication, cross-company account access, and safe artifact download. A basic CRUD-only API would also miss the requested report access, invoice PDF retrieval, invoice creation/finalization, and expense upload workflow.

## Proposed Outcome

- Add DRF API routing under `/api/` with OpenAPI schema/docs endpoints.
- Add account-owned API tokens using `Authorization: Bearer <token>`, stored hashed at rest and managed through admin/management commands.
- Scope all API access to the authenticated user account:
  - Normal users can access issuers linked through `Issuer.users`.
  - Superusers can access all issuers.
  - No endpoint should depend on `active_company_id` session state.
  - Reads may default to all accessible issuers; writes require an explicit issuer/company context when more than one issuer is available.
- Expose endpoints for:
  - `GET /api/me/` for account metadata and accessible issuer/company summaries.
  - `/api/issuers/` for connected issuer/company metadata and read-only invoice settings/bank-account context unless clarified otherwise.
  - `/api/customers/` and `/api/projects/` for account-scoped customer/project management.
  - `/api/invoices/` for list/filter/search/detail/create draft/update draft/delete draft, with nested order-line payloads.
  - `POST /api/invoices/{id}/finalize/` to move a draft invoice into the issued/finalized workflow where valid.
  - `POST /api/invoices/{id}/generate-pdf/` and `GET /api/invoices/{id}/pdf/` for generated invoice PDFs.
  - `/api/payments/` and payment application support for recording payments against accessible invoices.
  - `/api/expenses/` for creating/updating expenses with optional multipart attachment upload and attachment download.
  - `GET /api/reports/dashboard/` for account-level or issuer-filtered totals, recent activity, and monthly revenue/expense trend data.
- Include stable `id`, optional `external_id`, issuer/company metadata, timestamps, status, currency, amount, PDF/attachment availability, and relevant URLs in API responses.
- Add repo documentation covering authentication, token issuance/revocation, endpoint examples, filtering, errors, and artifact download behavior.

## Constraints / Non-Goals

- Do not make API credentials company-bound; tokens authenticate a user account and derive company access from that user’s connected issuers.
- Do not allow unsafe mutation or deletion of finalized/non-draft invoices. Non-draft invoice financial/content changes must be rejected through the API.
- Do not add OAuth/OIDC, public self-service token UI, or per-token scopes in this issue unless explicitly requested later.
- Do not expose direct media filesystem paths; stream permitted artifacts through authenticated API endpoints.
- Do not change existing browser UI active-company behavior.
- Pending the product/service open question, treat product/service support as invoice order-line payloads using the existing `OrderLine` model rather than adding a new catalog.
- Full incoming-email source management, backup management APIs, and UI visual changes are out of scope.

## Acceptance Criteria

### User Outcome

1. An authenticated external client can discover every issuer/company connected to the account and run reads across all accessible issuers or one selected issuer.
2. An authenticated external client can create a draft invoice with line items, update that draft, finalize it, and retrieve or request its PDF.
3. An authenticated external client can create expenses with optional attachments and retrieve permitted expense attachments.
4. An authenticated external client can retrieve report data that includes invoice, payment, and expense totals across accessible issuers.
5. API responses include stable IDs and enough metadata for external automation to reconcile records, select companies, and follow artifact URLs.

### Technical Behavior

1. `/api/` is served by DRF and includes OpenAPI schema/docs endpoints documenting auth, filters, actions, request bodies, and error responses.
2. Missing or invalid API tokens return JSON `401` responses instead of browser login redirects.
3. All querysets and object lookups are scoped to the authenticated account’s accessible issuers; inaccessible explicit issuer filters return a clear permission error and inaccessible object IDs are not exposed.
4. Invoice, customer, project, payment, and expense endpoints support pagination plus relevant filtering/search by issuer/company, status, date range, customer/project, and `external_id`.
5. Invoice create/update operations validate issuer/customer/project/bank-account consistency, save nested order lines transactionally, recalculate totals, and invalidate affected dashboard caches.
6. Finalized/non-draft invoices cannot be edited or deleted through the API; payment recording remains available through payment endpoints where domain rules allow it.
7. PDF and attachment endpoints stream only artifacts belonging to accessible issuers and return appropriate `404`/permission errors for missing or unauthorized files.
8. Expense uploads validate the same file type, size, project/customer, and report-exclusion rules used by the existing expense workflow.

### Operations / Deployment

1. New dependencies and database migrations are documented and apply cleanly in local, preview, and production environments.
2. No API tokens are created automatically during deploy; operators issue tokens intentionally and the plaintext token is shown only at creation time.
3. Existing browser routes, login/OTP flow, dashboards, invoice PDF rendering, and expense UI continue to work.
4. Runtime PDFs, attachments, databases, auth state, and generated media remain untracked and outside git.

### Validation

1. Tests cover token authentication, invalid/missing token responses, account/issuer scoping, and cross-company access for connected issuers.
2. Tests cover invoice list/detail/create/update draft/finalize/PDF download and finalized invoice mutation rejection.
3. Tests cover customer/project/payment permissions and error cases.
4. Tests cover report totals/trends across one issuer and multiple connected issuers.
5. Tests cover expense create/update with attachment upload/download and invalid attachment handling.
6. Tests verify OpenAPI schema generation succeeds and documents the protected endpoints.
7. `python manage.py test` and the repo’s canonical CI script pass.

## Implementation Plan

1. Add API infrastructure:
   - Add `djangorestframework` and an OpenAPI helper such as `drf-spectacular`.
   - Add a dedicated `api` Django app and include `path("api/", include("api.urls"))`.
   - Configure DRF authentication, permissions, pagination, schema metadata, and JSON error handling.
   - Exempt `/api/` from the browser login redirect middleware while keeping DRF permissions authoritative.
2. Add account API tokens:
   - Add an account-owned `ApiToken` model with hashed token secret, prefix, name, owner, created/last-used/revoked timestamps, and optional expiry.
   - Add admin and management commands to issue/revoke/list token metadata without reprinting stored secrets.
   - Add a DRF authentication class that accepts `Authorization: Bearer <token>`, authenticates the owner, rejects revoked/expired tokens, and updates `last_used_at`.
3. Add account-scoping utilities:
   - Centralize accessible issuer resolution from `request.user`.
   - Add helpers to resolve explicit `issuer_id`/company context for writes and reject out-of-scope IDs.
   - Ensure all serializers validate related objects against the same issuer scope.
4. Add resource serializers and viewsets:
   - Implement issuer/company metadata, customer, project, invoice, order-line, payment, payment-application, and expense serializers.
   - Use DRF routers for standard list/detail/create/update/delete where safe.
   - Keep issuer/company settings read-only unless the open question is answered in favor of write support.
5. Add invoice lifecycle actions:
   - Implement nested draft invoice creation and draft-only updates/deletes in transactions.
   - Implement finalization as an explicit action that moves valid drafts to the issued workflow and preserves invoice numbering/date rules.
   - Implement PDF generation and authenticated streaming actions using the existing PDF rendering behavior or a shared service extracted from it.
6. Add reports and artifacts:
   - Implement `/api/reports/dashboard/` using existing dashboard/date-filter semantics where practical, returning JSON totals, monthly trend data, and recent invoice/payment/expense summaries.
   - Add expense attachment upload/download support through authenticated endpoints.
7. Add documentation and tests:
   - Document token lifecycle, auth header format, endpoint examples, filters, common errors, PDF download, expense upload, and report behavior.
   - Add focused API tests for auth, permissions, success cases, finalized invariants, reports, uploads, and schema generation.

## Task List

- [ ] Add account token authentication and API routing
  - [ ] Add DRF/OpenAPI dependencies and REST framework settings.
  - [ ] Add the `api` app, `/api/` URL include, schema/docs routes, pagination, and JSON error handling.
  - [ ] Add the account API token model, migration, admin registration, and issue/revoke management commands.
  - [ ] Add Bearer-token authentication tests for valid, missing, invalid, revoked, and expired tokens.

- [ ] Add account-scoped resource serializers and viewsets
  - [ ] Add shared issuer-scope helpers for account-wide reads and explicit issuer/company write context.
  - [ ] Implement issuer/company metadata plus customer/project serializers and endpoints.
  - [ ] Implement invoice serializers with nested order-line create/update support.
  - [ ] Implement payment and payment-application endpoints with invoice amount recalculation coverage.
  - [ ] Add list/detail/filter/search and cross-account permission tests for each resource family.

- [ ] Add invoice lifecycle and PDF actions
  - [ ] Enforce draft-only invoice update/delete behavior in serializers/viewsets.
  - [ ] Implement the invoice finalization action with transaction safety and cache invalidation.
  - [ ] Implement invoice PDF generation and authenticated PDF streaming actions.
  - [ ] Add tests for finalized invoice immutability, PDF generation/download, and unauthorized artifact access.

- [ ] Add reports and expense upload endpoints
  - [ ] Implement account-level and issuer-filtered dashboard report JSON.
  - [ ] Implement expense create/update with multipart attachment upload and attachment download.
  - [ ] Reuse existing expense validation rules for file types, size limits, and project/customer consistency.
  - [ ] Add tests for multi-issuer report totals, date filtering, expense uploads, invalid files, and attachment permissions.

- [ ] Document the API contract
  - [ ] Add API documentation with token setup, auth headers, endpoint examples, filters, errors, and artifact download examples.
  - [ ] Link the API documentation from the README or docs index.
  - [ ] Ensure generated OpenAPI output includes authentication, request bodies, response metadata, and custom actions.

## Deployment / Rollout

- Apply new Python dependencies and run migrations before issuing tokens.
- Issue API tokens only after deploy through the documented management command or admin flow; store the plaintext token externally because it cannot be recovered later.
- Smoke-check that unauthenticated `/api/` data endpoints return JSON `401`, a valid token can call `/api/me/`, and an out-of-scope issuer is rejected.
- Verify PDF generation still has the required WeasyPrint runtime dependencies in the target environment.
- Run `python manage.py test` and `scripts/ci.sh` before release.

## File-Level Changes

### Add

- `api/` app with URLs, authentication, permissions, pagination, serializers, viewsets, report services, and tests.
- `accounts/migrations/0004_api_token.py` or the next available migration for account API tokens.
- `accounts/management/commands/issue_api_token.py`.
- `accounts/management/commands/revoke_api_token.py`.
- `docs/api.md`.

### Modify

- `requirements.txt` to add DRF/OpenAPI dependencies.
- `app/settings.py` for installed apps, DRF/OpenAPI config, and `/api/` login-exempt behavior.
- `app/urls.py` to include API routes.
- `accounts/models.py` and `accounts/admin.py` for API token storage/admin.
- `README.md` or `docs/README.md` to link API documentation.
- Invoice/expense service modules as needed to share PDF/report/upload behavior between UI and API without changing UI behavior.

### Keep

- Existing browser UI templates, static assets, and active-company session workflow.
- Existing generated media/runtime files untracked.
- Managed automation files and demo/visual scripts unless implementation specifically needs committed API validation helpers.

## Open Questions

- Should issuer/company settings be writable in this first API, or should issuer/company endpoints be read-only selection and metadata endpoints for this issue?
- Should product/service support be limited to invoice order-line payloads that use the existing `OrderLine` model, or should this issue add a standalone product/service catalog?
- Should expense uploads in this issue include only direct expense records with optional attachments, or also the existing CSV/XLS/XLSX/ZIP statement import workflow through the API?
