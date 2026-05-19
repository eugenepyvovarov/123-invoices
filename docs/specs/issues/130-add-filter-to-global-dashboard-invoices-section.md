## Overview

Add dashboard-level filtering to the existing global/cross-company dashboard Recent invoices section, plus a shared max-results selector for the Recent invoices and Recent payments blocks.

Assumption: “Global dashboard” refers to the existing cross-company dashboard shown in the issue screenshot, not the per-company dashboard.

## Problem

The global dashboard currently shows recent invoices using only the top date filter and a fixed result count. Users cannot narrow the Recent invoices block to unpaid/overdue invoices from the dashboard, and both recent dashboard blocks have a hard-coded limit that cannot be adjusted or preserved across refreshes.

## Proposed Outcome

- Add a right-aligned invoice status filter to the global dashboard Recent invoices card header, matching the existing invoice list status options and visual treatment.
- Apply the selected invoice status together with the existing top date filter.
- Add a `Max results` select to both the Recent invoices and Recent payments card headers.
- Use one shared max-results value for both blocks; changing it in either block updates both blocks.
- Support max-results options `25`, `50`, and `100`, defaulting to `25`.
- Persist `date_range`, invoice status, and max results in session-backed state between refreshes.
- Keep the existing per-company dashboard and invoice list behavior unchanged.

## Constraints / Non-Goals

- Do not redesign the dashboard beyond the requested filter controls.
- Do not change KPI, chart, payment, or expense calculations; invoice status filtering only affects the Recent invoices list.
- Do not add database fields or migrations.
- Reuse existing invoice status semantics, including derived overdue behavior and the combined `Invoiced & Overdue` option.
- Keep result limits bounded to `25`, `50`, and `100`.
- Follow existing grouped filter/button styling patterns used by the invoice list.

## Acceptance Criteria

### User Outcome

1. A signed-in user can open the global dashboard and see a status filter aligned to the right side of the Recent invoices title area.
2. Selecting an invoice status updates Recent invoices to match that status while still respecting the selected top date filter.
3. Selecting `Invoiced & Overdue` provides the dashboard-level unpaid/open-invoice view requested in the issue.
4. A user can change max results from either Recent invoices or Recent payments, and both blocks reflect the same selected limit.
5. Refreshing the page preserves the selected date range, invoice status, and max-results value.

### Technical Behavior

1. Dashboard invoice status options match the invoice list values and labels: `All`, `Draft`, `Invoiced`, `Invoiced & Overdue`, `Overdue`, and `Paid`.
2. The dashboard uses dashboard-specific GET/session state such as `invoice_status` and `max_results`; invalid values fall back safely to `all` and `25`.
3. Status filtering is applied after issuer access scoping and date filtering, before ordering/limiting recent invoices.
4. The shared max-results value applies to both recent invoice and recent payment queries with allowed values `25`, `50`, and `100`.
5. Cross-company dashboard cache behavior includes the selected status and max-results state, or otherwise prevents stale recent table data when filters change.
6. Existing invoice and customer links from the global dashboard continue to switch/open the correct company-scoped destination.

### Operations / Deployment

1. No schema migration is required.
2. Existing sessions without the new keys fall back to `all` status and `25` max results.
3. Standard deploy/build behavior is sufficient; collect static assets if CSS changes are made.
4. Rollback requires only reverting code and static changes; no data cleanup is needed.

### Validation

1. Django tests cover status filtering, combined `Invoiced & Overdue` filtering, shared max-results behavior, session persistence, invalid-value fallback, and cache separation/staleness.
2. Template/view tests verify the new controls render on the global dashboard and not as a per-company dashboard requirement.
3. Playwright coverage exercises the visible dashboard filter flow and captures the demo/visual checkpoints declared below.
4. Existing cross-company dashboard, invoice list, and per-company dashboard regression tests continue to pass.

## Implementation Plan

1. Extract or reuse invoice status option definitions so the invoice list and global dashboard stay aligned.
2. Add a small dashboard filter-state helper for `invoice_status` and `max_results` that validates GET input, writes valid values to session, and exposes active values/options to the template.
3. Update `cross_company_dashboard` to apply the selected invoice status to the recent invoice queryset and the shared max-results value to both recent invoice and recent payment queries.
4. Update cross-company dashboard cache keying or cached payloads so filter changes cannot reuse stale recent table ids.
5. Update `cross_company_dashboard.html` card headers with right-aligned invoice status controls and max-results selects, preserving the current table layout and empty states.
6. Add focused Django tests and an issue-specific Playwright spec for the visible filter/max-results flow.

## Task List

- [x] Add reusable dashboard filter state
  - [x] Define dashboard invoice status options from the existing invoice list status values.
  - [x] Define max-results options `25`, `50`, and `100` with default `25`.
  - [x] Add session-backed parsing/validation for `invoice_status` and `max_results`.
  - [x] Add tests for valid selection, invalid fallback, and refresh persistence.

- [x] Apply filters and limits in the global dashboard backend
  - [x] Apply selected invoice status to the cross-company recent invoice queryset.
  - [x] Apply the shared max-results value to recent invoices and recent payments.
  - [x] Preserve existing ordering, issuer scoping, and date-range behavior.
  - [x] Update cache keying/payload behavior to account for status and max-results state.
  - [x] Add backend tests for status/date combinations, shared limits, and cache freshness.

- [x] Update the global dashboard UI controls
  - [x] Add the right-aligned status toggle group to the Recent invoices card header.
  - [x] Add synchronized max-results selects to Recent invoices and Recent payments.
  - [x] Preserve current selected filters when any dashboard filter form submits.
  - [x] Add or adjust responsive styles only where needed.
  - [x] Add template assertions for controls, active state, and empty-state colspan safety.

- [x] Add preview-safe browser coverage and evidence capture
  - [x] Add an issue-specific Playwright spec for the global dashboard invoice filters.
  - [x] Exercise changing invoice status and max results from both dashboard blocks.
  - [x] Exercise page reload persistence from a reviewer-visible dashboard state.
  - [x] Capture the declared full-page checkpoints using existing evidence helpers.

## Deployment / Rollout

Deploy through the normal Django application path. No migration or backfill is expected. Existing users will see default `all` status and `25` max results until they choose different values.

If CSS changes are made, ensure static assets are collected as part of the normal build. After rollout, spot-check the global dashboard with a multi-company user and confirm that changing date, status, and max results persists after refresh.

## File-Level Changes

### Add

- `tests/e2e/cross-company-dashboard-invoice-filters.spec.js` — preview-safe browser coverage and evidence capture for the global dashboard filter flow.

### Modify

- `invoices/views.py` — add dashboard filter-state handling, apply status/max-results to cross-company recent tables, and update cache behavior.
- `invoices/templates/invoices/cross_company_dashboard.html` — add status and max-results controls to the relevant card headers.
- `invoices/static/invoices/css/design/components.css` — adjust dashboard card-header/filter layout if existing styles are insufficient.
- `invoices/tests/test_invoices.py` — add focused backend/template coverage for filtering, limits, persistence, and cache behavior.

### Keep

- `invoices/templates/invoices/dashboard.html` — per-company dashboard remains out of scope.
- `invoices/templates/invoices/view_invoices.html` — existing invoice list filter UI remains behaviorally unchanged.
- Invoice, payment, expense, and issuer models — no schema changes expected.

## Demo Media

### Scenario: cross-company-dashboard-invoice-filters

#### Repo Command

PLAYWRIGHT_VIDEO=on OPENCODE_DEMO_SCENARIO=cross-company-dashboard-invoice-filters ./scripts/e2e.sh tests/e2e/cross-company-dashboard-invoice-filters.spec.js --project=chromium

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow and open the global dashboard.
2. Change the Recent invoices status filter to a non-default invoice status option.
3. Change the max-results value from one dashboard block and confirm the other block reflects the same selected value.
4. Reload the dashboard and leave it in the reviewer-visible state with the selected filters still active.

#### Screenshot Checkpoints

- dashboard-invoice-status-filter-active: full-page screenshot of the global dashboard with the Recent invoices status filter active
- dashboard-shared-max-results-persisted: full-page screenshot of the global dashboard after reload with shared max-results selection still visible

## Visual Validation

### Identifier

cross-company-dashboard-invoice-filters

### Capture Command

./scripts/e2e.sh tests/e2e/cross-company-dashboard-invoice-filters.spec.js --project=chromium

### Steps

1. Sign in through the repo-owned smoke-user flow and open the global dashboard.
2. Capture the reviewer-visible dashboard state with the Recent invoices status controls and both max-results controls visible.

### Full-Page Checkpoints

- dashboard-invoice-filters-full-page: full-page screenshot of the global dashboard showing the updated Recent invoices and Recent payments card controls

### Expected Comparisons

- The `dashboard-invoice-filters-full-page` baseline/current pair should show the new right-aligned invoice status filter and shared max-results controls without unrelated dashboard layout changes.

### Baseline SHA

`ab270be1f187778c7af532822934f665edb864af`


## Open Questions

None.
