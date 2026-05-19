# Overview

Remove the `Project` column from the `Recent invoices` and `Recent payments` tables on `/dashboard/cross-company/` only. This should be a narrow UX cleanup that keeps the rest of the cross-company dashboard content, ordering, and behavior unchanged.

# Problem

The cross-company dashboard currently gives `Project` its own column in both recent-activity tables. On this aggregate page, that extra column adds width and visual noise without being required for the requested overview, making the tables harder to scan.

# Proposed Outcome

Update the two recent tables on the cross-company dashboard so they no longer render a dedicated `Project` header or project cell.

Expected post-change table shapes:

- `Recent invoices`: `#`, `Company`, `Date`, `Status`, `Client`, `Total`
- `Recent payments`: `Date`, `Company`, `Invoice`, `Client`, `Amount`

This change should:

- remove project-specific links/cells from those two tables
- preserve the remaining columns in their current order
- preserve existing non-project links, values, ordering, filters, and formatting
- avoid moving project information into another column as a replacement

# Constraints / Non-Goals

- Scope is limited to `/dashboard/cross-company/`.
- Do not change the per-company dashboard or any other invoice/payment table.
- Do not change dashboard KPIs, chart behavior, row ordering, row limits, or filtering.
- Do not add replacement project text to other columns.
- Do not expand this into a broader dashboard refactor; any supporting cleanup should stay behavior-neutral.

# Acceptance Criteria

## User Outcome

1. On `/dashboard/cross-company/`, the `Recent invoices` table no longer shows a visible `Project` column.
2. On `/dashboard/cross-company/`, the `Recent payments` table no longer shows a visible `Project` column.
3. The remaining columns in both tables stay in their current order, and existing non-project links and values continue to work as before.

## Technical Behavior

1. The change only affects the cross-company dashboard table markup; per-company dashboard output and other list/detail pages remain unchanged.
2. Existing recent-row ordering, result limits, data formatting, and table `data-testid` hooks remain unchanged.
3. Empty-state rows use the correct reduced column counts after the `Project` column is removed from each table.

## Operations / Deployment

1. The change ships without migrations, settings changes, cache-key changes, or feature-flag work.
2. The implementation PR remains compatible with the managed demo-evidence workflow by using only the spec-declared Playwright command.
3. Rollout follows the normal application deploy path for template and test updates.

## Validation

1. Server-side dashboard render coverage verifies both tables omit the `Project` column and keep the expected remaining headers.
2. Automated validation covers the updated empty-state table structure after the column removal.
3. A Playwright scenario validates the cross-company dashboard path and captures the named screenshot checkpoints from this spec.
4. Relevant existing dashboard and company-switch tests continue to pass.

# Demo Scenario

**Source-of-truth note:** Reuse is not implicit for this issue. Do not rely on older dashboard or company-switch Playwright coverage unless this spec is explicitly updated to point to it. Add and use the scenario below for demo evidence.

- **Scenario ID:** `cross-company-dashboard-no-project-columns`
- **Command:** `./scripts/e2e.sh tests/e2e/cross-company-dashboard-recent-tables.spec.js`
- **User-visible steps:**
  1. Seed the repo-owned E2E smoke data and open the app with the standard Playwright login flow.
  2. Sign in and land on the default company dashboard.
  3. Open the company switcher and choose `Dashboard` to navigate to `/dashboard/cross-company/`.
  4. Confirm the cross-company page shows `Recent invoices` with headers `#`, `Company`, `Date`, `Status`, `Client`, and `Total`, and no `Project` column.
  5. Confirm recent invoice rows still show their existing non-project links and values.
  6. Confirm `Recent payments` shows headers `Date`, `Company`, `Invoice`, `Client`, and `Amount`, and no `Project` column.
  7. Confirm recent payment rows still show their existing non-project links and values.
- **Screenshot checkpoints:**
  - `cross-company-dashboard-selected`
  - `recent-invoices-without-project-column`
  - `recent-payments-without-project-column`
- **Recorded evidence:**
  - The same spec-declared command must be the path used by the managed demo workflow to attach the scenario video and named screenshots to the implementation PR.

# Implementation Plan

1. Update `invoices/templates/invoices/cross_company_dashboard.html` to remove the `Project` header and per-row project cell from the `Recent invoices` table, and correct its empty-state `colspan`.
2. Update the same template to remove the `Project` header and per-row project cell from the `Recent payments` table, and correct its empty-state `colspan`.
3. Extend cross-company dashboard render tests to assert the new table shapes and absence of the removed column.
4. Add the dedicated Playwright scenario for the cross-company dashboard path and required screenshot checkpoints.

# Task List

- [x] Remove the project column from the recent invoices table
  - [x] Remove the `Project` header from the `Recent invoices` table markup.
  - [x] Remove the project cell/link from each recent invoice row.
  - [x] Update the `Recent invoices` empty-state `colspan` from 7 to 6.
  - [x] Extend cross-company dashboard render tests to assert the invoices table no longer includes `Project` and keeps the remaining headers.

- [x] Remove the project column from the recent payments table
  - [x] Remove the `Project` header from the `Recent payments` table markup.
  - [x] Remove the project cell/link from each recent payment row.
  - [x] Update the `Recent payments` empty-state `colspan` from 6 to 5.
  - [x] Extend cross-company dashboard render tests to assert the payments table no longer includes `Project` and keeps the remaining headers.

- [x] Add demo coverage for the visible dashboard change
  - [x] Add `tests/e2e/cross-company-dashboard-recent-tables.spec.js` for the spec-defined cross-company dashboard scenario.
  - [x] Capture the `cross-company-dashboard-selected` screenshot checkpoint.
  - [x] Capture the `recent-invoices-without-project-column` screenshot checkpoint.
  - [x] Capture the `recent-payments-without-project-column` screenshot checkpoint.

# Deployment / Rollout

This is a low-risk UI-only change.

Rollout should use the normal deploy path. Validation in local QA or staging should use a user with access to multiple companies and confirm:

- `/dashboard/cross-company/` still loads normally
- both recent tables no longer show a `Project` column
- remaining columns and links still behave the same way
- empty-state rows stay visually aligned after the reduced column counts
- the implementation PR includes the video and named screenshots from the spec-defined Playwright command

# File-Level Changes

## Add

- `tests/e2e/cross-company-dashboard-recent-tables.spec.js` — issue-specific Playwright scenario for the cross-company dashboard table cleanup

## Modify

- `invoices/templates/invoices/cross_company_dashboard.html` — remove the `Project` column from both recent tables and fix empty-state column spans
- `invoices/tests/test_invoices.py` — extend cross-company dashboard render assertions for the updated table markup

## Keep

- `invoices/views.py` — no cross-company aggregation or routing behavior changes are expected
- `invoices/urls.py` — the cross-company dashboard route remains unchanged
- `invoices/templates/invoices/dashboard.html` — the per-company dashboard remains unchanged
- `scripts/e2e.sh` and `playwright.config.js` — reuse the existing Playwright runner/config for the spec-defined command

# Open Questions

None.
