# Overview

Remove the `Total spending` KPI block from the dashboard so the remaining dashboard cards read more cleanly and the page no longer promotes a metric that is not currently useful.

# Problem

The issue request is to remove the `Total spending` block because it is not useful right now and the other dashboard blocks will look better without it.

Repository inspection shows this metric is not just template text:

- `invoices/templates/invoices/dashboard.html` renders a dedicated `Total spending` KPI card.
- `invoices/views.py` computes `total_spending` from `Expense` rows and stores it in the dashboard cache payload.
- Expense drawer copy still refers to “dashboard totals” / “dashboard spending totals,” which becomes misleading once the dashboard no longer exposes this metric.

If only the card is removed, the dashboard would still spend time calculating and caching an unused value, and related expense UI copy would point to a dashboard behavior users can no longer see.

# Proposed Outcome

Remove the `Total spending` KPI from the dashboard and simplify the dashboard context so it no longer computes or caches `total_spending`.

Also remove or update adjacent user-facing expense copy that specifically references dashboard spending totals, so the UI does not describe a dashboard feature that no longer exists.

# Constraints / Non-Goals

- Do not redesign the dashboard beyond removing the `Total spending` KPI and any directly dependent copy.
- Do not remove the expenses feature, expense records, or expense management screens.
- Do not introduce a replacement spending visualization in this issue.
- Do not change dashboard cache duration or unrelated KPI behavior.
- Keep all remaining monetary displays at two decimal places.

# Acceptance Criteria

## User Outcome

1. The dashboard no longer shows a `Total spending` KPI card for any period filter.
2. The remaining dashboard KPI cards continue to render cleanly without broken spacing or empty gaps.
3. Users do not see expense-form copy that refers to dashboard spending totals if that dashboard metric has been removed.

## Technical Behavior

1. The dashboard view no longer computes `total_spending` for dashboard rendering.
2. The dashboard cache payload no longer stores an unused `total_spending` value.
3. Removing this metric does not change the existing calculations for pending, overdue, invoiced, paid, recent invoices, or trend data.

## Operations / Deployment

1. The change ships as a code-only rollout with no migration or data backfill.
2. Existing expense data and any `exclude_from_reports` values remain intact unless explicitly unused copy is updated.
3. Dashboard cache refresh after deploy is sufficient for users to stop seeing the removed KPI.

## Validation

1. Automated coverage verifies the dashboard response and rendered HTML no longer expose `Total spending`.
2. Automated coverage verifies the remaining dashboard KPIs still render successfully.
3. Manual validation confirms the dashboard layout remains coherent across at least one populated company and one company with limited data.

# Implementation Plan

1. Remove the `Total spending` KPI markup from the dashboard template.
2. Remove `Expense` aggregation for `total_spending` from the dashboard context builder and cached payload.
3. Review expense-related labels that mention dashboard spending totals and update or remove that copy so it matches the new product behavior.
4. Add regression coverage for dashboard rendering without the spending KPI.

# Task List

- [x] Remove dashboard spending KPI
  - [x] Delete the `Total spending` card from `invoices/templates/invoices/dashboard.html`.
  - [x] Confirm the KPI grid still renders correctly with the remaining cards.
  - [x] Add or update a dashboard test that asserts `Total spending` is absent from the rendered page.

- [x] Remove unused dashboard spending aggregation
  - [x] Delete the `Expense` query and `total_spending` aggregation from `_build_dashboard_context`.
  - [x] Remove `total_spending` from the dashboard cache payload and returned context.
  - [x] Update or add a test covering successful dashboard rendering after the context change.

- [x] Align adjacent expense copy
  - [x] Update the expense form label in `expenses/forms.py` so it no longer references dashboard spending totals.
  - [x] Update matching expense drawer template copy if needed to stay consistent with the revised label.
  - [x] Add or update the relevant expense view test if label rendering is covered there.

# Deployment / Rollout

This should be a normal code-only release.

Operationally, the only runtime effect is dashboard cache turnover. After deploy, users may continue to see the old card until the cached dashboard entry expires or is refreshed. No schema, data, or background job changes are required.

Post-release verification should confirm:

1. the dashboard no longer shows `Total spending`
2. the remaining KPI cards render normally
3. expense entry UI no longer references dashboard spending totals

# File-Level Changes

- Modify `invoices/templates/invoices/dashboard.html` to remove the `Total spending` KPI card.
- Modify `invoices/views.py` to stop calculating and caching `total_spending` for the dashboard.
- Modify `expenses/forms.py` to remove or revise copy that refers to dashboard spending totals.
- Modify `expenses/templates/expenses/partials/expense_drawer.html` only if template-level label text or helper copy must stay aligned with the form change.
- Modify `invoices/tests/test_invoices.py` or the most relevant dashboard test module to cover the removed KPI.
- Keep `invoices/models.py` and existing expense data structures unless implementation proves the `exclude_from_reports` field is now fully dead and separately approved for removal.

# Open Questions

None.
