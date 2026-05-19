# Overview

Add a separate cross-company dashboard for the current user that aggregates data across every company they can access, without changing the existing per-company dashboard. The new page should be reachable from the company dropdown as `Dashboard` and should keep the same general dashboard feel: period filter, summary KPIs, and recent activity tables.

# Problem

The app currently scopes the dashboard to the active company only. Users with access to multiple companies cannot quickly see combined financial activity or the latest invoices and payments across their full portfolio. They must switch companies repeatedly and reconstruct the bigger picture manually.

# Proposed Outcome

Create a new cross-company dashboard view that:

- includes data from all issuers available to the signed-in user
- preserves the existing per-company dashboard at `/` and `/dashboard/`
- is reachable from the company dropdown via a dedicated `Dashboard` entry
- uses the existing global date filter semantics
- shows a familiar KPI + recent activity layout, but scoped to cross-company data

V1 should intentionally stay narrow:

- KPI cards for `Total income` and `Total expenses`
- latest invoices across companies
- latest payments across companies
- clear company context on every cross-company row
- links from cross-company rows should open the correct existing detail page while switching the active company to the row’s company first

Recommended metric definitions for V1:

- `Total income`: sum of `Payment.base_currency_amount` within the selected date range
- `Total expenses`: sum of `Expense.amount` within the selected date range
- invoice rows: newest first by `issued_date`, then `number/id`
- payment rows: newest first by `received_at`, then `id`

# Constraints / Non-Goals

- Do not replace or redesign the existing per-company dashboard.
- Do not add reporting-builder behavior, custom filters, or cross-company drilldown analytics.
- Do not change unrelated invoice, payment, or expense calculation rules.
- Do not introduce company-mixing behavior into existing company-scoped list/detail pages.
- V1 should not try to port every current dashboard widget; reuse the structure, not the full feature set.

# Acceptance Criteria

## User Outcome

1. A signed-in user with access to multiple companies can open a separate cross-company dashboard from the company dropdown via a `Dashboard` entry.
2. The existing per-company dashboard remains available and unchanged in purpose.
3. The cross-company dashboard shows combined `Total income` and `Total expenses` for the selected global date range.
4. The cross-company dashboard shows recent invoices and recent payments from across the user’s accessible companies.
5. Each invoice and payment row clearly identifies the company it belongs to.

## Technical Behavior

1. The page only includes issuers the current user is allowed to access.
2. Cross-company totals use existing persisted monetary fields suitable for aggregation across issuers, specifically `Payment.base_currency_amount` for income and `Expense.amount` for expenses.
3. The page respects the existing global date filter session/query behavior used elsewhere in the app.
4. Recent invoice and payment lists are ordered consistently and limited to a reasonable dashboard-sized result set.
5. Navigating from a cross-company row to an existing company-scoped detail page updates active company context to the row’s issuer before rendering the destination page.
6. Existing per-company dashboard routes, behavior, and template output remain intact.

## Operations / Deployment

1. The change ships without a schema migration unless implementation uncovers a missing persisted field required for safe aggregation.
2. Any caching added for cross-company dashboard data uses separate keys from the existing per-company dashboard cache.
3. Dashboard invalidation behavior covers cross-company dashboard data when invoices, payments, or expenses affecting the view change.

## Validation

1. Automated tests cover access control for users with one or many issuers.
2. Automated tests verify cross-company KPI aggregation, recent invoice ordering, recent payment ordering, and company labels in row output.
3. Automated tests verify dropdown access to the new page and that row navigation lands in the correct company context.
4. Existing dashboard and company-switching tests continue to pass.

# Implementation Plan

1. Add a dedicated route and view for the cross-company dashboard, separate from the existing `dashboard` view.
2. Build a cross-company query layer that derives the current user’s available issuers, applies the global date range, and computes:
   - total income from payments
   - total expenses from expenses
   - recent invoices with issuer/company metadata
   - recent payments with issuer/company metadata and related invoice references when available
3. Add a new dashboard template that reuses the current dashboard page structure patterns but trims V1 content to the required cross-company KPIs and recent tables.
4. Update the company dropdown UI so it includes a dedicated `Dashboard` destination without altering the existing company switch behavior.
5. Add a safe navigation path from cross-company rows into existing company-scoped detail views by switching the active company before redirecting.
6. Add regression and feature tests around aggregation, access boundaries, navigation, and dropdown visibility.

# Task List

- [x] Add cross-company routing and aggregation backend
  - [x] Add a named route and view for the cross-company dashboard
  - [x] Build issuer-scoped cross-company queries using the current user’s available issuers
  - [x] Aggregate total income from `Payment.base_currency_amount` for the selected range
  - [x] Aggregate total expenses from `Expense.amount` for the selected range
  - [x] Add tests for issuer access boundaries and KPI totals

- [x] Add recent activity datasets and navigation behavior
  - [x] Build recent invoice queryset with company metadata and deterministic ordering
  - [x] Build recent payment queryset with company metadata and deterministic ordering
  - [x] Add a redirect mechanism that switches active company before opening company-scoped detail pages
  - [x] Add tests for invoice/payment ordering, company labels, and row navigation

- [x] Add the dashboard UI entry points and template
  - [x] Add a dedicated cross-company dashboard template using the existing dashboard layout conventions
  - [x] Render KPI cards for total income and total expenses with two-decimal formatting
  - [x] Render recent invoices and recent payments tables with explicit company columns
  - [x] Add the `Dashboard` entry to the company dropdown
  - [x] Add template/view tests covering dropdown access and rendered sections

- [x] Protect existing dashboard behavior
  - [x] Keep the current per-company dashboard route and template behavior unchanged
  - [x] Namespace any new cache keys separately from the current dashboard keys
  - [x] Extend invalidation to clear cross-company dashboard cache data when relevant records change
  - [x] Run dashboard and company-switch regression tests

# Deployment / Rollout

- No database migration is expected for the V1 cut.
- Release as a normal application deploy.
- Verify in staging or local QA with a user linked to at least two issuers and distinct invoices, payments, and expenses.
- Post-deploy checks should confirm:
  - per-company dashboard still renders normally
  - company dropdown shows the new `Dashboard` destination
  - cross-company totals match fixture/admin data for the selected period
  - cross-company row navigation lands in the expected company context

# File-Level Changes

## Add

- `invoices/templates/invoices/cross_company_dashboard.html`

## Modify

- `invoices/urls.py` — add the cross-company dashboard route and any helper redirect route needed for row navigation
- `invoices/views.py` — add cross-company dashboard context builder, navigation redirect logic, and cache/invalidation support
- `invoices/templates/invoices/navbar.html` — add the dropdown entry for the cross-company dashboard
- `invoices/tests/test_invoices.py` and/or a dedicated dashboard test module — add cross-company aggregation and rendering coverage
- `invoices/tests/test_company.py` — extend company-switch/navigation coverage for cross-company entry points

## Keep

- `invoices/templates/invoices/dashboard.html` — remains the per-company dashboard
- Existing company-scoped list/detail templates and routes — remain company-scoped in V1

# Open Questions

None.
