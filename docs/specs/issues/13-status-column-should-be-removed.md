# Overview

Remove the `Status` column from the invoices list table for every status filter state. The status filter controls remain available, but the table itself should no longer render a status header or per-row status badge.

# Problem

The invoices list currently renders the `Status` column inconsistently: it is already hidden for the combined `Invoiced & Overdue` filter but still appears for `All`, `Draft`, `Invoiced`, `Overdue`, and `Paid`. The issue and screenshots indicate that this is the wrong UX cut. The table should use one consistent column set across all status views.

# Proposed Outcome

Update the invoices list so the table columns are always:

- selection
- invoice number
- date
- client
- project
- total

This applies regardless of the selected status filter. Existing status-based filtering behavior should continue to determine which invoices are shown, but status should no longer be repeated inside the table rows.

# Constraints / Non-Goals

- Keep the status filter toggle group; only remove the table column.
- Do not change invoice status logic, derived overdue logic, or combined filter behavior.
- Do not redesign the invoices page layout beyond the column removal.
- Do not remove status badges from invoice detail, edit, dashboard, customer, or project views unless they are part of the invoices list table.

# Acceptance Criteria

## User Outcome

1. When viewing the invoices list with any status filter selected, the table does not show a `Status` column.
2. When viewing the invoices list with any status filter selected, each invoice row omits the status badge cell.
3. Users can still filter invoices by status using the existing status filter controls.

## Technical Behavior

1. The invoices list view builds one consistent invoice table column definition for all status filters.
2. The rendered row cell count matches the header count for every status filter state.
3. Existing total and outstanding amount formatting remains unchanged, including two-decimal currency display and overdue/current styling in the total column.

## Operations / Deployment

1. The change requires no database migration, data backfill, or admin action.
2. The change is safe to deploy as a template/view update with no feature flag.

## Validation

1. Automated tests cover the invoices list for `all`, `draft`, `invoiced`, `invoiced,overdue`, `overdue`, and `paid` filter states and verify the `Status` column is absent.
2. Automated tests confirm the invoices list still returns the correct filtered records after the column removal.
3. Manual verification confirms the table layout matches the intended screenshots except for the removed status column across all filter states.

# Implementation Plan

1. Simplify the invoices list view logic so the table column definition no longer conditionally inserts a `Status` column.
2. Remove per-row status cell construction from the invoices list row builder.
3. Update or replace tests that currently assert the status column is present for non-combined filters.
4. Manually verify all status tabs to ensure filtering still works and totals/outstanding amounts render correctly after the column count change.

# Task List

- [x] Simplify invoices list table structure
  - [x] Remove the conditional `show_status_column` table header logic from `view_invoices`.
  - [x] Remove the per-row status cell from the invoices list row construction.
  - [x] Confirm the empty-state colspan still aligns with the final header count.

- [x] Update invoices list coverage
  - [x] Replace the non-combined filter test expectation so all filters assert the same header set without `Status`.
  - [x] Keep combined-filter coverage focused on its filtered results and total-column behavior rather than special column handling.
  - [x] Run the relevant Django test coverage for the invoices list view.

- [x] Validate UI behavior
  - [x] Manually verify `All`, `Draft`, `Invoiced`, `Invoiced & Overdue`, `Overdue`, and `Paid` views render without a status column.
  - [x] Manually verify status filters still change the invoice results correctly.

# Deployment / Rollout

Deploy as a standard application release. No migrations are required. After deploy, verify the invoices list in production for each status filter to confirm the table header and row structure are consistent and that bulk selection plus total/outstanding amount rendering still behave normally.

# File-Level Changes

- Modify `invoices/views.py`
  - Remove conditional status-column assembly from the invoices list context.
  - Remove status cell injection from invoice row generation.

- Modify `invoices/tests.py`
  - Update invoices list tests so all status filters assert the shared no-status-column table shape.
  - Preserve assertions for status filtering behavior and total/outstanding rendering.

- Keep `invoices/templates/invoices/view_invoices.html`
  - No structural change expected if the table continues to render from `order_columns` and `invoice_rows`.

- Keep `invoices/templates/invoices/partials/data_table.html`
  - No change expected; it should continue rendering the provided columns and cells.

# Open Questions

None.
