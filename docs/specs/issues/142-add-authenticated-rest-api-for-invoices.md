## Overview

Add an authenticated, account-scoped Django REST Framework API under `/api/` so external tools and a future HTTP MCP server can safely work with invoices without direct database or filesystem access. This should go beyond basic CRUD by supporting connected companies, reports, invoice PDFs, invoice creation/finalization, payments, customers/projects, and expense uploads.

## Problem

The app is currently browser/session-oriented and uses an active company in UI session state. Server-to-server tools need token authentication, stable JSON responses, account-level access across all companies connected to the user, safe artifact downloads, and workflow operations that preserve invoice invariants.

## Proposed Outcome

- Add DRF routing under `/api/` with OpenAPI schema/docs endpoints.
- Assumption: “account” maps to the authenticated Django user and its linked issuers through `Issuer.users`; superusers can access all issuers.
- Add account-bound Bearer tokens stored hashed at rest, with admin/management-command lifecycle support.
- Scope API access to the authenticated account, not the active browser company session.
- Expose endpoints for:
  - `GET /api/me/` with account metadata and accessible issuer/company summaries.
  - Read-only issuer/company selection metadata, including bank-account context.
  - Customers, projects, invoices with order lines, payments/payment applications, and expenses.
  - Invoice lifecycle actions: finalize, generate PDF, and authenticated PDF download.
  - Expense creation/update with optional multipart attachment upload and authenticated attachment download.
  - Dashboard-style reports across accessible issuers or filtered to selected issuers.
- Include stable IDs, optional `external_id`, issuer/company metadata, timestamps, statuses, currency/amount metadata, artifact availability, and followable API URLs.
- Document auth, token creation/revocation, endpoint examples, filters, errors, reports, PDFs, and expense upload.

Resolved open-question decisions from issue comments:
- Question: Should issuer/company settings be writable in this first API, or should issuer/company endpoints be read-only metadata and selection endpoints for now?
  Decision: Issuer/company settings should be read-only metadata and selection endpoints in this first API. Do not add writable issuer/company settings yet.
  Source comments: #19369
  Reason: The comment explicitly states that issuer/company settings should be read-only metadata and selection endpoints for the first API.
- Question: Should product/service support use the existing invoice order-line fields only, or should this issue add a standalone product/service catalog API and backing model?
  Decision: Product/service support should use the existing invoice order-line fields only. Do not add a standalone product/service catalog in this issue.
  Source comments: #19369
  Reason: The comment explicitly states that product/service support should use the existing invoice order-line fields only and not add a standalone catalog.
- Question: Should expense uploads include only direct expense records with optional attachments, or should this issue also expose the existing CSV/XLS/XLSX/ZIP statement import workflow through the API?
  Decision: Expense uploads should cover direct expense records with optional attachments only. Do not expose the existing CSV/XLS/XLSX/ZIP statement import workflow in this issue.
  Source comments: #19369
  Reason: The comment explicitly limits expense uploads to direct expense records with optional attachments, excluding the statement import workflow for this issue.
- Question: Are dashboard-style report endpoints for totals, monthly revenue/expense trends, receivables status, and recent activity sufficient for this first API, or are specific additional report outputs required?
  Decision: Dashboard-style report endpoints for totals, monthly revenue/expense trends, receivables status, and recent activity are sufficient for this first API. Do not add extra specialized report families unless a later issue asks for them.
  Source comments: #19369
  Reason: The comment confirms that the listed dashboard-style reports are sufficient for the first API and advises against adding extra specialized reports.

## Constraints / Non-Goals

- API credentials must be account/user-bound, not company-bound.
- API endpoints must not depend on `active_company_id` or browser session state.
- Assumption: invoice statuses `invoiced`, `overdue`, and `paid` are finalized/non-draft for API immutability.
- Do not permit unsafe mutation or deletion of finalized/non-draft invoices.
- Do not expose direct media filesystem paths; stream permitted artifacts through authenticated endpoints.
- Do not add OAuth/OIDC, public self-service token UI, or per-token scopes in this issue.
- Do not change existing browser UI active-company behavior.
- Do not add incoming-email source management, backup APIs, or UI visual changes.
- Do not add specialized report families, a standalone product/service catalog, or statement-import APIs unless clarified in Open Questions.

## Acceptance Criteria

### User Outcome

1. An authenticated external client can discover every issuer/company connected to the account and run reads across all accessible issuers or one selected issuer.
2. An authenticated external client can create a draft invoice with order lines, update that draft, finalize it, and request/download its PDF.
3. An authenticated external client can manage customers, projects, payments, and direct expense records with optional attachments.
4. An authenticated external client can retrieve account-level and issuer-filtered report data.
5. Finalized invoices cannot be edited or deleted through the API.

### Technical Behavior

1. `/api/` is served by DRF and includes schema/docs endpoints.
2. Bearer-token authentication returns JSON `401` responses for missing, invalid, expired, or revoked tokens instead of browser redirects.
3. All querysets and object lookups are scoped to the authenticated account’s accessible issuers.
4. Reads support pagination plus relevant filtering/search by issuer, status, date range, customer/project, and `external_id`.
5. Invoice create/update validates issuer/customer/project/bank-account consistency, saves nested order lines transactionally, recalculates totals, and invalidates dashboard caches.
6. Finalization uses an explicit API action and prevents later non-draft mutation/deletion.
7. PDF and attachment endpoints stream only artifacts belonging to accessible issuers.
8. OpenAPI output includes authentication, request bodies, response metadata, and custom actions.

### Operations / Deployment

1. New dependencies and migrations apply cleanly in local, preview, and production environments.
2. No API tokens are created automatically during deploy.
3. Plaintext token values are shown only at creation time.
4. Existing browser routes, login/OTP flow, dashboards, invoice PDF rendering, and expense UI continue to work.
5. Runtime PDFs, attachments, databases, auth state, and generated media remain untracked.

### Validation

1. Tests cover token authentication, invalid/missing tokens, revoked/expired tokens, account scoping, and cross-company access.
2. Tests cover invoice list/detail/create/update draft/finalize/PDF download and finalized invoice mutation rejection.
3. Tests cover customer, project, payment, permission, and error cases.
4. Tests cover report totals/trends across one issuer and multiple connected issuers.
5. Tests cover expense create/update with attachment upload/download and invalid attachment handling.
6. Tests verify OpenAPI schema generation succeeds.
7. `python manage.py test` and `scripts/ci.sh` pass.

## Implementation Plan

1. Add DRF, OpenAPI, and filtering dependencies; create an `api` app with router, pagination, schema/docs routes, and JSON error behavior.
2. Exempt `/api/` from browser login redirects while letting DRF authentication/permissions control data endpoints.
3. Add an account-owned API token model with hashed secret, prefix, name, owner, timestamps, revoked state, optional expiry, admin registration, and management commands.
4. Centralize accessible-issuer resolution for API requests using `Issuer.users` and superuser access.
5. Implement serializers/viewsets for account metadata, issuers, customers, projects, invoices/order lines, payments/applications, expenses, and reports.
6. Implement invoice lifecycle actions for draft-only mutation, finalization, PDF generation, and authenticated PDF streaming.
7. Implement expense multipart upload/download using existing attachment validation rules.
8. Add API documentation and focused tests for auth, scoping, workflows, reports, artifacts, uploads, and schema generation.

## Task List

- [x] Add REST API foundation and account tokens
  - [x] Add DRF/OpenAPI/filtering dependencies and REST framework settings.
  - [x] Add the `api` app, `/api/` URL include, router, schema/docs routes, pagination, and JSON error handling.
  - [x] Exempt `/api/` from login middleware redirects without weakening browser routes.
  - [x] Add API token model, migration, admin registration, and issue/list/revoke management commands.
  - [x] Add authentication tests for valid, missing, invalid, revoked, and expired tokens.

- [x] Add account-scoped resource endpoints
  - [x] Add shared issuer-scope helpers for account-wide reads and explicit issuer write validation.
  - [x] Implement `me`, issuer/company metadata, bank-account metadata, customer, and project serializers/endpoints.
  - [x] Add filtering, searching, pagination, and stable response metadata.
  - [x] Add permission and cross-account isolation tests for resource endpoints.

- [x] Add invoice workflow and PDF actions
  - [x] Implement invoice serializers with nested order-line create/update support.
  - [x] Enforce draft-only invoice update/delete behavior in API serializers/viewsets.
  - [x] Implement invoice finalization, total recalculation, cache invalidation, and PDF generation/download actions.
  - [x] Add tests for invoice lifecycle success cases, finalized immutability, PDF download, and unauthorized artifact access.

- [x] Add payments, reports, and expense uploads
  - [x] Implement payment and payment-application endpoints with invoice amount/status recalculation.
  - [x] Implement account-level and issuer-filtered dashboard report JSON.
  - [x] Implement expense create/update with multipart attachment upload and attachment download.
  - [x] Add tests for payments, multi-issuer reports, expense uploads, invalid files, and attachment permissions.

- [x] Document the API contract
  - [x] Add `docs/api.md` with token setup, auth headers, endpoint examples, filters, errors, reports, PDFs, and expense upload examples.
  - [x] Link API documentation from the README or docs index.
  - [x] Ensure OpenAPI annotations describe auth, request bodies, response fields, and custom actions.

## Deployment / Rollout

- Apply new Python dependencies and migrations before issuing tokens.
- Issue API tokens only after deploy through the documented management command or admin flow.
- Smoke-check unauthenticated API data endpoints return JSON `401`, a valid token can call `/api/me/`, and out-of-scope issuer access is rejected.
- Verify PDF generation still has the required WeasyPrint runtime dependencies.
- Run `python manage.py test` and `scripts/ci.sh` before release.

## File-Level Changes

### Add

- `api/` app with URLs, authentication, permissions, pagination, serializers, viewsets, report helpers, and tests.
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
- `accounts/middleware.py`.
- Invoice/expense service modules as needed to share PDF, report, payment recalculation, and upload validation behavior.
- `README.md` or `docs/README.md`.

### Keep

- Existing browser UI templates, static assets, and active-company session workflow.
- Existing generated media/runtime files untracked.
- Managed automation files and demo/visual scripts unless implementation specifically needs committed API validation helpers.

## Open Questions

None.
