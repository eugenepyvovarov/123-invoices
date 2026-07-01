## Overview

Add an authenticated, account-scoped Django REST Framework API under `/api/` so external tools and a future HTTP MCP server can safely work with invoices without direct database or filesystem access. The API should authenticate as a user account, expose every issuer/company connected to that account, and support invoice creation/finalization, invoice PDFs, customers, projects, payments, reports, and expense uploads.

## Problem

The current app is browser/session-oriented and centered on the active company in the UI session. Server-to-server tools and AI agents need stable JSON endpoints, token authentication, cross-company account access, safe artifact downloads, and workflow operations beyond basic CRUD.

## Proposed Outcome

- Add DRF routing under `/api/` with OpenAPI schema/docs endpoints.
- Add account-owned Bearer tokens stored hashed at rest and managed through admin/management commands.
- Scope all API access to the authenticated user account:
  - Normal users access issuers linked through `Issuer.users`.
  - Superusers access all issuers.
  - API endpoints do not depend on `active_company_id` session state.
  - Reads may default to all accessible issuers; writes require explicit issuer/company context when needed.
- Expose endpoints for:
  - `GET /api/me/` for account metadata and accessible issuer/company summaries.
  - `/api/issuers/` for connected company metadata and read-only invoice/bank-account context unless clarified otherwise.
  - `/api/customers/`, `/api/projects/`, `/api/invoices/`, `/api/payments/`, and `/api/expenses/`.
  - `POST /api/invoices/{id}/finalize/`.
  - `POST /api/invoices/{id}/generate-pdf/` and `GET /api/invoices/{id}/pdf/`.
  - `GET /api/reports/dashboard/` for account-level or issuer-filtered totals, recent activity, and monthly revenue/expense trend data.
  - Expense create/update with optional multipart attachment upload and authenticated attachment download.
- Include stable `id`, optional `external_id`, issuer/company metadata, timestamps, status, currency, amounts, artifact availability, and relevant API URLs in responses.
- Add repo documentation for auth, token lifecycle, endpoint examples, filters, errors, PDF download, expense upload, and reports.

## Constraints / Non-Goals

- API credentials must be account/user-bound, not company-bound.
- Do not allow unsafe mutation or deletion of finalized/non-draft invoices.
- Do not add OAuth/OIDC, public self-service token UI, or per-token scopes in this issue.
- Do not expose direct media filesystem paths; stream permitted artifacts through authenticated API endpoints.
- Do not change existing browser UI active-company behavior.
- Do not add specialized report families beyond dashboard/cross-company totals, trends, and recent activity in this first cut.
- Do not add a standalone product/service catalog unless the open question is answered in favor of it.
- Do not include CSV/XLS/XLSX/ZIP statement-import APIs unless the open question is answered in favor of it.
- Full incoming-email source management, backup management APIs, and UI visual changes are out of scope.

## Acceptance Criteria

### User Outcome

1. An authenticated external client can discover every issuer/company connected to the account and run reads across all accessible issuers or one selected issuer.
2. An authenticated external client can create a draft invoice with line items, update that draft, finalize it, and retrieve or request its PDF.
3. An authenticated external client can create expenses with optional attachments and retrieve permitted expense attachments.
4. An authenticated external client can retrieve report data across accessible issuers.
5. API responses include stable IDs and enough metadata for external automation to reconcile records, select companies, and follow artifact URLs.

### Technical Behavior

1. `/api/` is served by DRF and includes OpenAPI schema/docs endpoints.
2. Missing or invalid API tokens return JSON `401` responses instead of browser login redirects.
3. All querysets and object lookups are scoped to the authenticated account’s accessible issuers.
4. Resource endpoints support pagination plus relevant filtering/search by issuer, status, date range, customer/project, and `external_id`.
5. Invoice create/update validates issuer/customer/project/bank-account consistency, saves nested order lines transactionally, recalculates totals, and invalidates affected dashboard caches.
6. Finalized/non-draft invoices cannot be edited or deleted through the API; payment recording remains available where domain rules allow it.
7. PDF and attachment endpoints stream only artifacts belonging to accessible issuers.
8. Expense uploads reuse existing file type, size, project/customer, and report-exclusion rules.

### Operations / Deployment

1. New dependencies and migrations apply cleanly in local, preview, and production environments.
2. No API tokens are created automatically during deploy.
3. Plaintext token values are shown only at creation time.
4. Existing browser routes, login/OTP flow, dashboards, invoice PDF rendering, and expense UI continue to work.
5. Runtime PDFs, attachments, databases, auth state, and generated media remain untracked.

### Validation

1. Tests cover token authentication, invalid/missing tokens, account/issuer scoping, and cross-company access.
2. Tests cover invoice list/detail/create/update draft/finalize/PDF download and finalized invoice mutation rejection.
3. Tests cover customer/project/payment permission and error cases.
4. Tests cover report totals/trends across one issuer and multiple connected issuers.
5. Tests cover expense create/update with attachment upload/download and invalid attachment handling.
6. Tests verify OpenAPI schema generation succeeds.
7. `python manage.py test` and `scripts/ci.sh` pass.

## Implementation Plan

1. Add API infrastructure with `djangorestframework`, an OpenAPI helper such as `drf-spectacular`, an `api` app, `/api/` URL include, pagination, schema metadata, and JSON error handling.
2. Exempt `/api/` from browser login redirects while keeping DRF permissions authoritative.
3. Add an account-owned `ApiToken` model with hashed token secret, prefix, name, owner, created/last-used/revoked timestamps, and optional expiry.
4. Add admin and management commands to issue, list, and revoke token metadata without reprinting stored secrets.
5. Centralize accessible issuer resolution from `request.user` and explicit issuer/company validation for writes.
6. Implement serializers/viewsets for issuer metadata, customers, projects, invoices/order lines, payments/applications, expenses, and dashboard reports.
7. Implement invoice lifecycle actions for draft-only mutation, finalization, PDF generation, and authenticated PDF streaming.
8. Implement expense multipart upload/download using existing attachment validation rules.
9. Document the API contract and add focused tests for auth, permissions, workflows, reports, artifacts, uploads, and schema generation.

## Task List

- [ ] Add account token authentication and API routing
  - [ ] Add DRF/OpenAPI dependencies and REST framework settings.
  - [ ] Add the `api` app, `/api/` URL include, schema/docs routes, pagination, and JSON error handling.
  - [ ] Add the account API token model, migration, admin registration, and token management commands.
  - [ ] Add Bearer-token authentication tests for valid, missing, invalid, revoked, and expired tokens.

- [ ] Add account-scoped resource serializers and viewsets
  - [ ] Add shared issuer-scope helpers for account-wide reads and explicit issuer/company write context.
  - [ ] Implement issuer/company metadata plus customer/project serializers and endpoints.
  - [ ] Implement invoice serializers with nested order-line create/update support.
  - [ ] Implement payment and payment-application endpoints.
  - [ ] Add list/detail/filter/search and cross-account permission tests for each resource family.

- [ ] Add invoice lifecycle and PDF actions
  - [ ] Enforce draft-only invoice update/delete behavior in serializers/viewsets.
  - [ ] Implement invoice finalization with transaction safety and cache invalidation.
  - [ ] Implement invoice PDF generation and authenticated PDF streaming actions.
  - [ ] Add tests for finalized invoice immutability, PDF generation/download, and unauthorized artifact access.

- [ ] Add reports and expense upload endpoints
  - [ ] Implement account-level and issuer-filtered dashboard report JSON.
  - [ ] Implement expense create/update with multipart attachment upload and attachment download.
  - [ ] Reuse existing expense validation rules for file types, size limits, and project/customer consistency.
  - [ ] Add tests for multi-issuer reports, date filtering, expense uploads, invalid files, and attachment permissions.

- [ ] Document the API contract
  - [ ] Add API documentation with token setup, auth headers, endpoint examples, filters, errors, and artifact download examples.
  - [ ] Link the API documentation from the README or docs index.
  - [ ] Ensure generated OpenAPI output includes authentication, request bodies, response metadata, and custom actions.

## Deployment / Rollout

- Apply new Python dependencies and run migrations before issuing tokens.
- Issue API tokens only after deploy through the documented management command or admin flow.
- Smoke-check that unauthenticated `/api/` data endpoints return JSON `401`, a valid token can call `/api/me/`, and an out-of-scope issuer is rejected.
- Verify PDF generation still has the required WeasyPrint runtime dependencies.
- Run `python manage.py test` and `scripts/ci.sh` before release.

## File-Level Changes

### Add

- `api/` app with URLs, authentication, permissions, pagination, serializers, viewsets, report services, and tests.
- `accounts/migrations/0004_api_token.py` or the next available migration.
- `accounts/management/commands/issue_api_token.py`.
- `accounts/management/commands/revoke_api_token.py`.
- `accounts/management/commands/list_api_tokens.py`.
- `docs/api.md`.

### Modify

- `requirements.txt`.
- `app/settings.py`.
- `app/urls.py`.
- `accounts/models.py`.
- `accounts/admin.py`.
- `README.md` or `docs/README.md`.
- Invoice/expense service modules as needed to share PDF/report/upload behavior between UI and API.

### Keep

- Existing browser UI templates, static assets, and active-company session workflow.
- Existing generated media/runtime files untracked.
- Managed automation files and demo/visual scripts unless implementation specifically needs committed API validation helpers.

## Open Questions

- Should issuer/company settings be writable in this first API, or should issuer/company endpoints be read-only selection and metadata endpoints for this issue?
- Should product/service support be limited to invoice order-line payloads that use the existing `OrderLine` model, or should this issue add a standalone product/service catalog?
- Should expense uploads in this issue include only direct expense records with optional attachments, or also the existing CSV/XLS/XLSX/ZIP statement import workflow through the API?
