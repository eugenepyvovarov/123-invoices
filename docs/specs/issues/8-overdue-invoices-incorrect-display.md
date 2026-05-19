# Overview

Refine the invoice list display for the combined `Invoiced & Overdue` filter so the table matches the intended behavior shown on the project Activity tab: remove the redundant status column for that view and show the outstanding amount as a second line in the Total column, using red for overdue balances and default text color for not-yet-overdue unpaid balances.

# Problem

The invoice list for `/invoices/?status=invoiced,overdue...` currently shows a `Status` column that is not needed for this review workflow. At the same time, the `Total` column does not consistently communicate how much remains unpaid versus how much is overdue.

This creates two issues:

1. The table spends a full column on status even though the user is reviewing only invoiced/open items.
2. The more important information—the outstanding amount and whether it is overdue—is not presented the same way as on the project Activity tab.

There is also a consistency risk because the list currently decides whether to render the extra amount note from the stored status value instead of the derived overdue state already used elsewhere in the app.

# Proposed Outcome

For the invoice list when the selected status filter is `Invoiced & Overdue`:

- Remove the `Status` column from the table.
- Show the invoice total on the first line of the `Total` column.
- When an invoice still has an outstanding balance, show a second line in parentheses with that outstanding amount.
- Render that second line in red when the outstanding balance is overdue.
- Render that second line in the normal/current styling when the balance is unpaid but not overdue.
- Use the same derived overdue logic already used across project/customer activity views so display stays aligned across surfaces.

# Constraints / Non-Goals

- Do not change invoice filtering behavior or which invoices appear in the combined filter.
- Do not change the project Activity tab behavior; use it as the display reference.
- Do not introduce new invoice statuses or persistence changes.
- Keep all money formatting at two decimals.
- Do not broaden this into a full invoice list redesign.
- Do not remove the status column from other invoice-list filter views unless required by the current combined-filter implementation.

# Acceptance Criteria

## User Outcome

1. When a user opens the invoice list with the `Invoiced & Overdue` filter selected, the table does not show a `Status` column.
2. In that same view, each invoice row shows the main total on the first line of the `Total` column.
3. If an invoice has an unpaid balance, the `Total` column shows a second line in parentheses with that unpaid amount.
4. The second-line amount is visually red when the balance is overdue and visually non-red when the balance is unpaid but not overdue.

## Technical Behavior

1. The invoice list uses the same derived overdue rule used elsewhere in the application rather than relying only on the stored `status` field for this display.
2. The extra amount note is rendered only when the outstanding amount is greater than zero.
3. All rendered monetary values in this view use two-decimal formatting.
4. Table column definitions and row cell generation stay aligned so headers and row data remain structurally correct after the status column is removed for the combined-filter view.

## Operations / Deployment

1. The change does not require database migrations, data backfills, or configuration changes.
2. Existing invoice list behavior for other status filters continues to render without layout regressions.

## Validation

1. Automated tests cover the combined `Invoiced & Overdue` view without the status column.
2. Automated tests cover second-line total rendering for both overdue and not-yet-overdue unpaid invoices.
3. Automated tests confirm the combined-filter view remains consistent with derived overdue behavior.

# Implementation Plan

1. Update the invoice list view context so column configuration is conditional for the combined `invoiced,overdue` filter.
2. Build the `Total` cell from outstanding balance data using the derived display state already calculated for each invoice.
3. Reuse the existing amount-note styling pattern from customer/project activity views for red vs current-state secondary amounts.
4. Add view-level tests that assert the combined-filter table structure and rendered total-cell content.

# Task List

- [x] Adjust combined-filter table structure
  - [x] Make invoice list column definitions omit `Status` when `status=invoiced,overdue`
  - [x] Update invoice row cell construction so row cells match the conditional header layout
  - [x] Verify the non-combined invoice list filters still receive the existing column set

- [x] Align total-column rendering with derived outstanding state
  - [x] Build the `Total` cell secondary line from `amount_due` when the outstanding balance is greater than zero
  - [x] Apply overdue/current styling from the derived display state instead of the stored raw status
  - [x] Keep the total and secondary outstanding amount formatted with two decimals

- [x] Add regression coverage
  - [x] Add a test that the combined `Invoiced & Overdue` list omits the `Status` header
  - [x] Add a test that an overdue invoice shows a red parenthetical outstanding amount in the `Total` column
  - [x] Add a test that an invoiced but not-overdue invoice shows a non-red parenthetical outstanding amount in the `Total` column

# Deployment / Rollout

This is a template/view-layer change with test updates only. No migration or staged rollout is needed.

After deployment, validate the combined `Invoiced & Overdue` invoice list in the browser against the project Activity tab reference to confirm:

- the status column is absent,
- totals still align correctly,
- overdue notes are red,
- unpaid but current notes are not red.

# File-Level Changes

- **Modify** `invoices/views.py` to make invoice list columns and total-cell rendering conditional for the combined status filter and to use derived overdue display state consistently.
- **Modify** `invoices/tests.py` to cover combined-filter column layout and total-cell note rendering for overdue vs unpaid-current invoices.
- **Keep** `invoices/templates/invoices/project_detail.html` as the visual/reference pattern for the secondary amount note behavior unless a shared partial is later justified.
- **Keep** database models and migrations unchanged.

# Open Questions

None.
