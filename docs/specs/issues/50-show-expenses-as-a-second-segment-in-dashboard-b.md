# Overview

Extend the existing 36-month dashboard bar chart so each monthly bar shows both invoiced totals and reportable expense totals in the same stacked bar. The expense segment should use orange and the chart should stay clear that it compares invoiced amounts vs expenses, not profit.

# Problem

The dashboard chart currently shows only invoice totals, so users cannot compare monthly invoiced amounts against expenses in the main dashboard view. The issue scope also requires chart values to match the dashboard source data, and the newest feedback adds an important reporting rule: expenses marked **Exclude from reports** must not be counted in the chart.

Repository context shows the chart is built in `_build_dashboard_context()` in `invoices/views.py`, rendered in `invoices/templates/invoices/dashboard.html`, and the `Expense` model already has an `exclude_from_reports` flag.

# Proposed Outcome

Update the dashboard chart from a single-series column chart to a stacked two-series Charts.css chart where:

- invoiced totals remain the primary series
- expenses are added as a second stacked segment in orange
- expense totals are grouped by `paid_date`
- expenses with `exclude_from_reports=True` are excluded from the chart aggregation
- chart copy, legend, and accessible labels make the two series explicit
- cached dashboard data includes the new expense series and refreshes when relevant invoice or expense data changes

# Constraints / Non-Goals

- Do not redesign the rest of the dashboard or add new KPI cards.
- Do not add new chart types, interactivity, or profit/net calculations.
- Do not change unrelated invoice or expense business rules.
- Do not introduce a new charting library; keep Charts.css.
- Keep money display formatting at two decimals where amounts are shown.
- Keep the existing 36-month chart window unless implementation finds a repository-level blocker.
- Do not include expenses flagged `exclude_from_reports`; this chart should follow reportable-expense behavior only.

# Acceptance Criteria

## User Outcome

1. The dashboard chart shows both invoiced totals and expenses for each displayed month within the same bar.
2. The expense segment is visually distinct and uses orange.
3. The chart title, caption, and legend clearly distinguish invoiced amounts from expenses without implying profit or net balance.
4. The chart remains readable for months with only invoiced data, only expense data, both, or neither.

## Technical Behavior

1. Dashboard context includes one chart payload covering the same 36-month month range for both invoiced totals and expense totals.
2. The invoiced series continues to aggregate non-draft invoices by `issued_date`.
3. The expense series aggregates `Expense.amount` by `paid_date` for the active issuer and excludes rows where `exclude_from_reports=True`.
4. Months with no values for one or both series are still present in the chart payload with zero totals as needed for aligned rendering.
5. Dashboard caching accounts for expense-backed chart data so invoice or expense changes do not leave stale chart values in place.
6. The rendered chart uses Charts.css stacked multi-series markup rather than a custom visualization.

## Operations / Deployment

1. The change ships as a code-only rollout with no schema migration or data backfill.
2. Existing expense records remain unchanged; only dashboard visualization and aggregation behavior are updated.
3. Post-deploy cache behavior is sufficient to show updated chart values after normal dashboard use and after expense mutations.

## Validation

1. Automated coverage verifies dashboard context contains both monthly invoiced totals and monthly reportable expense totals.
2. Automated coverage verifies expenses marked `exclude_from_reports=True` are not counted in the chart series.
3. Automated coverage verifies rendered dashboard HTML includes the updated chart copy, legend, and stacked two-series structure.
4. Manual validation confirms the stacked chart renders correctly with the orange expense segment and expected values for a known month.

# Implementation Plan

1. Extend dashboard aggregation to build aligned monthly invoice and expense totals across the existing 36-month window.
2. Filter the expense aggregation to reportable expenses only by excluding `exclude_from_reports=True`.
3. Replace the invoice-only trend payload with a combined chart payload that supports stacked rendering, legend text, and accessible per-month labels.
4. Update dashboard caching so expense changes participate in cache freshness for the chart payload.
5. Update the dashboard template and CSS to render the stacked chart and legend using Charts.css conventions.
6. Add regression coverage for aggregation rules, excluded-expense behavior, rendered markup, and cache freshness.

# Task List

- [x] Build combined dashboard chart data
  - [x] Add monthly expense aggregation in `invoices/views.py` using `paid_date` and `amount` for the active issuer.
  - [x] Exclude expenses where `exclude_from_reports=True` from the monthly expense aggregation.
  - [x] Refactor the invoice-only trend payload into a combined month-aligned chart structure for invoiced and expense values.

- [x] Make dashboard cache reflect expense-backed chart data
  - [x] Update dashboard cache versioning or signature inputs so expense create/update/delete can invalidate or bypass stale chart entries.
  - [x] Store the combined chart payload in the cached dashboard context.
  - [x] Add a regression test that proves expense changes are reflected after cache use.

- [x] Render the stacked dashboard chart
  - [x] Replace the single-series chart markup in `invoices/templates/invoices/dashboard.html` with a Charts.css stacked multi-series chart.
  - [x] Add chart copy and legend text that labels the blue invoiced series and orange expense series clearly.
  - [x] Add accessible labels so each month exposes both invoiced and expense values in rendered HTML.

- [x] Add styling and regression coverage
  - [x] Update `invoices/static/invoices/css/base.css` for stacked chart presentation, legend layout, and orange expense styling.
  - [x] Add a dashboard test covering one month with invoiced totals, included expenses, and excluded expenses.
  - [x] Add a rendering test asserting the updated chart copy, legend, and two-series markup.

# Deployment / Rollout

This is a normal code-only release.

Rollout notes:

1. No migration, data repair, or background job changes are required.
2. Because the chart becomes expense-backed, deploy validation should include a known excluded expense to confirm it is not represented.
3. Post-release verification should confirm the dashboard shows stacked bars, orange expenses, and values that match reportable expense data rather than all expense records.

# File-Level Changes

- Modify `invoices/views.py` to aggregate monthly reportable expenses, build the combined chart payload, and update cache freshness inputs.
- Modify `invoices/templates/invoices/dashboard.html` to render a stacked Charts.css chart with clear series labeling and accessible text.
- Modify `invoices/static/invoices/css/base.css` to support stacked-series and legend styling, including the orange expense segment.
- Modify `invoices/tests/test_invoices.py` or the closest dashboard-focused test module to cover combined totals, excluded-expense behavior, rendered output, and cache handling.
- Keep `invoices/models.py` unchanged; the existing `Expense.exclude_from_reports` field should be reused.
- Keep expense create/update/delete flows unchanged unless a minimal cache-related touch-up is required to support correct dashboard freshness.

# Open Questions

None.
