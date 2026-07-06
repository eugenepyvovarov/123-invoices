## Overview

Normalize the vertical spacing around the select/download bulk action toolbar wherever that toolbar appears. The current UI shows the toolbar with page-level margin on some list pages and flush against neighboring content on others.

## Problem

The select/download toolbar is visually inconsistent across pages. Invoices render the toolbar as part of the page stack, while Expenses renders the same toolbar inside a nested results fragment, which can lose the same vertical gap before the table. This makes the same bulk action block look misaligned depending on the page.

## Proposed Outcome

A shared spacing pattern applies to every current select/download bulk toolbar instance so the toolbar has the same visible margin from surrounding filters, tables, and pagination across pages.

Assumption: “this block” refers to the `.sticky-toolbar` / `.bulk-toolbar` select-download toolbar currently used on the Invoices list and Expenses list; if implementation finds additional current instances of the same block, include them too.

## Constraints / Non-Goals

- Do not change bulk selection, download behavior, form targets, CSRF handling, generated PDFs, generated ZIPs, filters, sorting, pagination, or table data.
- Do not add one-off page-specific magic margins when a shared layout utility or component rule can solve the inconsistency.
- Do not add product behavior, hidden routes, or scenario-only source branches solely for evidence capture.
- Do not include the Expense CSV import row selector unless implementation confirms it is the same select/download toolbar pattern.

## Acceptance Criteria

### User Outcome

1. Every page with the select/download bulk toolbar shows consistent vertical spacing around the toolbar.
2. The Invoices and Expenses list pages no longer show one toolbar flush against adjacent content while another has a visible gap.
3. The toolbar remains visually usable when controls wrap on narrower screens.

### Technical Behavior

1. The spacing is implemented through shared CSS/layout conventions rather than duplicated per-page margin overrides.
2. Current `.sticky-toolbar` / `.bulk-toolbar` behavior remains intact, including sticky positioning where already intended.
3. Existing bulk action forms, checkbox selectors, button labels, and download actions continue to work unchanged.
4. Any duplicate or conflicting toolbar styling is consolidated only as needed to make the shared spacing predictable.

### Operations / Deployment

1. No database migration is required.
2. Static CSS/template changes deploy through the existing application deployment pipeline.
3. Rollback is safe by reverting the CSS/template changes.

### Validation

1. Django/template tests cover that the Invoices and Expenses list pages render the shared toolbar spacing hook or wrapper.
2. Playwright coverage opens the affected list pages and verifies the toolbar can be reached without relying on exact row counts.
3. Visual validation captures baseline/current full-page screenshots for the affected pages.

## Implementation Plan

1. Audit all current templates for `.sticky-toolbar`, `.bulk-toolbar`, and select/download bulk action forms.
2. Define the shared vertical spacing approach in the design component CSS or an existing stack utility.
3. Apply the shared spacing to direct page children and nested result fragments so both Invoices and Expenses inherit the same visual rhythm.
4. Preserve existing form ownership via `form="..."`, checkbox classes, and JavaScript bindings.
5. Add focused tests and visual validation coverage for the affected list pages.

## Task List

- [x] Normalize shared bulk-toolbar spacing
  - [x] Audit current select/download toolbar instances in invoice and expense templates.
  - [x] Add or reuse a shared stack/spacing class for toolbar-adjacent content.
  - [x] Update affected toolbar containers so nested fragments and direct page children use the same gap.
  - [x] Consolidate conflicting `.sticky-toolbar` styling if needed while preserving existing sticky behavior.

- [x] Preserve behavior and responsive layout
  - [x] Keep invoice and expense bulk action form targets, checkbox names, and download buttons unchanged.
  - [x] Confirm toolbar controls wrap cleanly on narrow viewports with the same surrounding gap.
  - [x] Add or update Django/template tests for the shared toolbar spacing hook on Invoices and Expenses.

- [x] Add issue-specific visual evidence support
  - [x] Add a Playwright visual capture spec for the Invoices and Expenses list pages.
  - [x] Wire `bulk-toolbar-spacing` into `scripts/visual-validation.sh`.
  - [x] Keep capture setup preview-safe and avoid exact seeded row-count assumptions.

## Deployment / Rollout

Deploy as a normal static/template-only application change. No migration or operator data action is needed. After deployment, a quick smoke check should open the Invoices and Expenses list pages and confirm the select/download toolbar spacing is consistent.

## Visual Validation

### Identifier

bulk-toolbar-spacing

### Capture Command

./scripts/visual-validation.sh bulk-toolbar-spacing

### Steps

1. Authenticate through the repo-owned Playwright flow.
2. Open the Invoices list page and capture the filter area, select/download toolbar, and beginning of the table.
3. Open the Expenses list page and capture the filter area, select/download toolbar, and beginning of the table.
4. In baseline mode, assert only that the existing pages and broad list containers load before capture.
5. In current mode, verify the shared toolbar spacing hook or wrapper is present before capture.

### Full-Page Checkpoints

- invoices-bulk-toolbar-spacing: full-page screenshot of the Invoices list with the select/download toolbar visible
- expenses-bulk-toolbar-spacing: full-page screenshot of the Expenses list with the select/download toolbar visible

### Expected Comparisons

- The `invoices-bulk-toolbar-spacing` baseline/current pair should preserve the toolbar while showing the normalized spacing if the page changed.
- The `expenses-bulk-toolbar-spacing` baseline/current pair should show the toolbar no longer flush against adjacent content.
- The current screenshots for both pages should show matching vertical rhythm around the same toolbar pattern.

## File-Level Changes

- Modify `invoices/static/invoices/css/design/components.css` to centralize the toolbar spacing and resolve conflicting toolbar rules if necessary.
- Modify `invoices/templates/invoices/view_invoices.html` only if the shared spacing hook requires markup alignment.
- Modify `expenses/templates/expenses/partials/expense_list_results.html` and/or `expenses/templates/expenses/expenses_list.html` so the nested results fragment uses the shared spacing.
- Modify `invoices/tests/test_invoices.py` and `expenses/tests/test_list_views.py` or nearby tests for template/render coverage.
- Add `tests/e2e/bulk-toolbar-spacing.spec.js` for visual validation capture.
- Modify `scripts/visual-validation.sh` to expose the `bulk-toolbar-spacing` identifier.
- Keep model files, migrations, download views, generated static output, media, screenshots, videos, and local runtime files unchanged.

## Open Questions

None.
