# Overview

Remove the redundant `Open` button from each invoice row on the invoices list screen. The invoice number already links to the invoice detail/edit view, so the extra button adds visual noise and duplicates navigation.

# Problem

A regression introduced an `Open` button beside each invoice number in the invoices list. This creates two problems:

1. It duplicates an action that is already available by clicking the invoice number.
2. It makes the row denser and less scannable without adding distinct value.

The current implementation also wires the button to the invoice drawer, which is a different interaction than the linked invoice number, making the row behavior less clear.

# Proposed Outcome

Each invoice row should use the invoice number link as the sole entry point to open that invoice from the list.

The invoices list should no longer render the per-row `Open` button or its drawer-trigger attributes. The rest of the row content, bulk selection, totals, filtering, and pagination should remain unchanged.

# Constraints / Non-Goals

- Do not redesign the invoices table layout beyond removing the redundant button.
- Do not change invoice navigation targets outside the invoices list.
- Do not remove or redesign the invoice drawer globally unless it becomes unused on this screen as a direct result of this change.
- Do not alter invoice filtering, bulk actions, totals, or pagination behavior.
- Do not introduce database, model, or API changes.

# Acceptance Criteria

## User Outcome

1. Each invoice row on the invoices screen no longer shows an `Open` button beside the invoice number.
2. Users can still open an invoice by clicking the invoice number link.
3. The invoices list remains readable and aligned after the button is removed.

## Technical Behavior

1. The invoice row markup for the invoices list no longer includes the per-row drawer trigger button or related `data-invoice-drawer` trigger attributes.
2. The invoice number continues to link to the existing invoice detail/edit route.
3. No unrelated invoice-list behaviors change, including bulk selection, totals display, filters, and pagination.

## Operations / Deployment

1. The change requires no migration, data backfill, or configuration update.
2. Deployment can proceed as a normal application release with no special rollout steps.

## Validation

1. Automated coverage verifies the invoices list response no longer renders the redundant `Open` button for invoice rows.
2. Automated coverage verifies invoice number links still point to the expected invoice route.
3. A manual UI check confirms the invoices screen matches the intended simplified row layout.

# Implementation Plan

1. Update the invoices list row construction so the number cell only renders the invoice sequence link.
2. Remove list-specific drawer-trigger markup that exists only to support the redundant `Open` button.
3. Add or update a view/template test to assert the row no longer contains the button text/trigger while preserving the invoice link.
4. Run the relevant invoices test coverage to confirm no regression in list rendering behavior.

# Task List

- [x] Simplify invoice row markup
  - [x] Update `invoices/views.py` so the invoice number cell renders only the invoice link
  - [x] Remove the list-row `Open` button markup and drawer-trigger attributes from the generated number cell

- [x] Validate invoices list rendering
  - [x] Add or update a test in `invoices/tests/test_invoices.py` that asserts the invoices list does not render the row-level `Open` button
  - [x] Add or update a test in `invoices/tests/test_invoices.py` that asserts the invoice number still links to the invoice edit/detail route

- [x] Confirm no unintended screen impact
  - [x] Manually verify the invoices list layout still aligns correctly after removing the button
  - [x] Run the targeted Django invoices tests covering the invoices list page

# Deployment / Rollout

This is a low-risk UI cleanup with no schema or data impact. Ship in a normal release.

Post-deploy validation should consist of loading the invoices page, confirming the `Open` button is absent from each row, and confirming invoice number links still navigate correctly.

# File-Level Changes

## Modify

- `invoices/views.py` — remove the redundant `Open` button from the invoice number cell markup used to build invoice rows.
- `invoices/tests/test_invoices.py` — add or update coverage for invoice list row rendering and invoice link behavior.

## Keep

- `invoices/templates/invoices/view_invoices.html` — keep overall page structure unless implementation chooses to move row rendering concerns out of the view later.
- `invoices/static/invoices/js/invoice_drawer.js` — keep unless follow-up cleanup shows the invoices list no longer needs any list-bound drawer trigger behavior.
- `invoices/templates/invoices/partials/invoice_drawer.html` — keep unless a separate cleanup removes unused drawer functionality from the page entirely.

# Open Questions

None.
