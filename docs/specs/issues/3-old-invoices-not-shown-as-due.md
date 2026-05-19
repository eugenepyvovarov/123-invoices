# Overview

Fix stale overdue display by deriving overdue state from each invoice's stored `due_date` and current unpaid balance at read time, then using that same rule on the invoice list and the related customer, project, and dashboard surfaces that currently read persisted overdue fields.

# Problem

The reported `/invoices/?status=invoiced%2Coverdue` view can show older unpaid invoices as merely invoiced because the page filters and labels from persisted `Invoice.status`, while an invoice can become overdue later without any write event.

Repository inspection confirms the bug is broader than one row label:

- `/invoices/` list filtering and status display use persisted `status`.
- Customer and project totals use persisted `amount_overdue`.
- Customer and project Activity tabs currently render any unpaid balance in red parentheses instead of distinguishing unpaid from overdue.
- The dashboard is cached for 300 seconds and still builds overdue totals/top-overdue lists from persisted overdue fields.
- The source of truth for "when due" already exists as stored `invoice.due_date`; this issue should not infer due-ness from invoice age.

# Proposed Outcome

Use one shared overdue rule everywhere this issue touches:

- overdue when `due_date < today` and `amount_due > 0`
- not overdue when `due_date` is today or later, or when the invoice is fully paid

Apply that rule to:

- `/invoices/` row status display
- `/invoices/` status filtering for `overdue` and `invoiced,overdue`
- customer and project pending/overdue totals and styling
- customer and project Activity tab unpaid parentheses, shown in black when unpaid but not overdue and red when overdue
- dashboard overdue totals and top-overdue widgets, while keeping the existing 300-second cache duration

# Constraints / Non-Goals

- Stored `due_date` remains authoritative; do not derive due dates from "one month after issue date."
- Do not redesign invoice creation, payment-term defaults, or due-date editing.
- Do not remove cached amount fields unless needed for this bug fix; the change is about read behavior consistency.
- Do not change dashboard cache duration as part of this issue.
- Keep monetary displays at two decimal places.
- Do not expand Activity tabs into a larger status-management UI beyond the requested unpaid/overdue color distinction.

# Acceptance Criteria

## User Outcome

1. An unpaid invoice with a stored `due_date` before today appears as overdue on `/invoices/`.
2. An unpaid invoice with a stored `due_date` of today or later appears as non-overdue on `/invoices/`.
3. The `/invoices/` `Overdue` and `Invoiced & Overdue` filters include the same invoices the list itself classifies as overdue or invoiced.
4. On customer and project Activity tabs, unpaid balances remain in parentheses, render in black when not yet overdue, and render in red when overdue.
5. Customer, project, and dashboard overdue totals match the same overdue rule used on `/invoices/`.

## Technical Behavior

1. Overdue classification is evaluated from `due_date < today` plus `amount_due > 0`, not from persisted `status` or `amount_overdue` alone.
2. `/invoices/` filtering and row labeling consume one shared overdue helper or annotation.
3. Customer, project, and dashboard overdue aggregates consume the same shared rule.
4. A previously unpaid invoice can become overdue on the correct day without any invoice or payment write occurring that day.
5. Existing outstanding-invoice selection behavior for payments continues to show unpaid invoices, while any overdue styling on those rows stays aligned with the shared rule if that surface is touched.

## Operations / Deployment

1. Deployment does not alter existing `due_date`, payment-term, or issued-date data.
2. Dashboard caching remains in place at the current short-lived duration.
3. If any remaining user-visible surface must still read persisted overdue fields after the change, rollout includes a safe refresh path for existing unpaid invoices.
4. Operators can verify one known past-due unpaid invoice and one unpaid-but-not-overdue invoice after release.

## Validation

1. Automated coverage verifies past-due, due-today, and future-due unpaid invoices.
2. Automated coverage verifies `/invoices/` row status and filter membership stay aligned.
3. Automated coverage verifies customer/project totals and Activity-tab color behavior stay aligned with the shared overdue rule.
4. Automated coverage verifies dashboard overdue totals or top-overdue membership no longer depend on stale persisted overdue state.
5. Manual validation confirms the originally reported invoice now appears overdue.

# Implementation Plan

1. Introduce a shared invoice overdue helper or queryset annotation that exposes a derived `is_overdue` value from `due_date` and `amount_due`.
2. Update `/invoices/` list filtering and status display to use the derived rule instead of persisted `status` alone.
3. Update customer and project aggregate queries and Activity row context to use the same derived rule for overdue totals and unpaid/overdue styling.
4. Update dashboard overdue totals and top-overdue selection to use the shared rule while preserving the existing cache window.
5. Audit remaining user-visible overdue reads of persisted `status` or `amount_overdue` and add a one-time refresh path only if any such reads must remain.

# Task List

- [x] Centralize overdue derivation
  - [x] Add a shared helper or queryset annotation for `is_overdue` based on `due_date < today` and `amount_due > 0`.
  - [x] Define the due-today boundary once and use it across read paths.
  - [x] Add focused tests for the shared overdue rule.

- [x] Fix invoice list behavior
  - [x] Update `/invoices/` status filtering for `overdue` and `invoiced,overdue` to use the shared rule.
  - [x] Update `/invoices/` row status text and badge state to use the same rule.
  - [x] Add regression tests for invoices that become overdue without a same-day write.

- [x] Align customer and project surfaces
  - [x] Replace customer overdue totals that sum `amount_overdue` with totals derived from the shared rule.
  - [x] Replace project overdue totals that sum `amount_overdue` with totals derived from the shared rule.
  - [x] Update customer and project Activity rows so unpaid parentheses are black when not overdue and red when overdue.
  - [x] Add cross-surface tests covering `/invoices/`, customer detail, and project detail consistency.

- [x] Align dashboard and rollout safety
  - [x] Update dashboard overdue totals and top-overdue selection to use the shared rule inside the existing cache build.
  - [x] Audit any remaining user-visible overdue reads that still depend on persisted overdue fields.
  - [x] Add a recalculation command or release step only if the audit finds a remaining persisted-field dependency.
  - [x] Document post-deploy verification for one overdue and one not-yet-overdue unpaid invoice.

# Deployment / Rollout

This should be a code-first bug-fix rollout.

The repository currently caches only the dashboard in this area, for 300 seconds. The invoice list, customer detail, and project detail are request-time views but still read stale persisted overdue fields. If all user-visible overdue displays are switched to the shared derived rule, release can remain code-only with normal cache expiry on the dashboard.

If any user-visible surface still depends on persisted `status` or `amount_overdue`, include a one-time refresh of existing unpaid invoices during rollout.

Post-release verification should confirm:

1. the reported past-due unpaid invoice is overdue on `/invoices/`
2. a due-today or future-due unpaid invoice remains non-overdue
3. customer/project Activity parentheses and totals match the same overdue rule
4. dashboard overdue totals and top-overdue items reflect the same corrected state after cache refresh or expiry

# File-Level Changes

- Add `invoices/services/invoice_state.py` or equivalent shared helper location for derived overdue logic and query helpers.
- Modify `invoices/views.py` to apply the shared rule in `/invoices/`, customer detail, project detail, and dashboard queries.
- Modify `invoices/templates/invoices/customer_profile.html` to distinguish unpaid versus overdue parentheses and any overdue total styling driven by derived state.
- Modify `invoices/templates/invoices/project_detail.html` to distinguish unpaid versus overdue parentheses and any overdue total styling driven by derived state.
- Modify `invoices/templates/invoices/dashboard.html` if template context or overdue presentation changes require it.
- Modify `invoices/tests.py` or split tests under `invoices/tests/` to cover derived overdue behavior, list/filter alignment, dashboard alignment, and Activity-tab styling.
- Keep `invoices/services/cached_totals.py` as the write-time cache updater unless the shared overdue helper should be reused there for consistency.
- Add `invoices/management/commands/...` only if rollout still needs a persisted-field refresh path.

# Open Questions

None at this time.
