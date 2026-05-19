# Overview

Fix the dashboard’s monthly invoiced-vs-expenses chart so each month renders as one readable bar, with reportable expenses shown as an orange portion within the blue invoiced total bar rather than as a separate side-by-side series.

# Problem

The current chart template uses a two-series Charts.css column layout (`multiple stacked`) that renders invoiced totals and expenses as separate cells per month. Combined with per-cell rotated labels, this makes the chart visually cluttered and breaks the intended month-by-month comparison. The underlying dashboard context already provides monthly invoiced, expense, and combined totals, but the current markup/CSS does not present them as a single monthly bar.

# Proposed Outcome

Render one bar per month using the existing 36-month dataset, where:

- the full bar height tracks the invoiced total for that month
- the expense amount renders as an orange overlay/segment inside that same monthly bar
- month labels remain the existing `M Y` category labels
- verbose per-series labels are removed from the visual chart surface while preserving accessible text/summary
- the chart remains readable across the existing dashboard time range without changing KPI behavior or dashboard filtering

# Constraints / Non-Goals

- Do not change the dashboard period filter, KPI calculations, or invoice/expense inclusion rules.
- Do not introduce a new charting library; keep using Charts.css-compatible markup/styling.
- Do not expand scope into cross-company dashboard behavior unless the same chart is already shared there.
- Do not add mobile-specific redesign beyond keeping current behavior intact.
- Do not change the blue invoiced and orange expense visual semantics.

# Acceptance Criteria

## User Outcome

1. Each month in the dashboard chart renders as a single monthly bar, not as separate invoiced and expense bars.
2. The orange expense amount appears within/overlaid on the same monthly bar as the invoiced total.
3. Month/category labels continue to display as simple month/year labels.
4. The chart is readable across the current dashboard time range without the current label-heavy clutter.

## Technical Behavior

1. The dashboard view continues to expose monthly invoiced and expense totals for the same 36-month window.
2. Chart rendering uses one visual column per month while preserving distinct styling for invoiced total and expense portion.
3. Accessible text still communicates the month, invoiced total, and expense total for each plotted month.
4. Existing caching behavior for dashboard chart data remains intact.
5. No database schema, migration, or reporting-rule changes are introduced.

## Operations / Deployment

1. The change deploys as an application/template/static asset update only.
2. Static asset collection continues to succeed without additional runtime configuration.
3. No manual data backfill or operational migration steps are required.

## Validation

1. Automated coverage verifies the dashboard context still returns correct monthly invoiced, expense, and combined totals.
2. Automated template/rendering coverage verifies the chart markup reflects one monthly bar with embedded expense presentation rather than two independent series cells.
3. Validation confirms the dashboard page remains readable with populated multi-month data.

# Implementation Plan

1. Update the dashboard chart markup to represent each month as one chart column and move expense rendering into nested/overlay content within that column.
2. Simplify chart CSS so labels, spacing, and bar treatment match the intended monthly comparison and remove rotated per-series label rendering.
3. Keep the existing server-side monthly aggregation path, but tighten any chart-specific fields needed to support single-bar rendering cleanly.
4. Replace tests that currently assert the two-series table structure with assertions for the new single-bar structure and preserved accessibility text.

# Task List

- [x] Reshape dashboard chart markup
  - [x] Replace the two-data-cell-per-month chart table structure in `dashboard.html` with a single rendered bar per month.
  - [x] Preserve month label output and screen-reader text for invoiced and expense totals in each month row/bar.
  - [x] Update chart legend/caption copy only where needed so it matches the new single-bar presentation.

- [x] Simplify chart styling for readability
  - [x] Remove the rotated per-cell visible label treatment from the dashboard chart CSS.
  - [x] Add styling for a blue monthly bar with an orange embedded expense segment/overlay.
  - [x] Tune spacing, sizing, and overflow behavior so the 36-month range remains readable.

- [x] Align chart data contract and regression coverage
  - [x] Keep or minimally adjust dashboard chart context fields required by the new single-bar template.
  - [x] Update dashboard tests that currently assert two-series markup to assert the new chart structure.
  - [x] Retain/add tests for monthly invoiced, expense, and combined totals plus accessible chart text.

# Deployment / Rollout

Deploy as a normal application release with static asset collection. No migration or feature flag is required. After deployment, verify the dashboard in a seeded or production-like dataset covering several months to confirm the chart remains readable and expenses render inside the monthly invoiced bars.

# File-Level Changes

## Modify

- `invoices/templates/invoices/dashboard.html` — replace the current two-series chart table markup with single-bar-per-month markup.
- `invoices/static/invoices/css/base.css` — remove cluttered label treatment and add styling for the embedded expense segment within each monthly bar.
- `invoices/tests/test_invoices.py` — update rendering assertions and preserve regression coverage for dashboard chart data/accessibility.
- `invoices/views.py` — only if needed to simplify or clarify chart-specific context fields for the updated template.

## Keep

- Dashboard KPI calculations and date-range filtering logic outside the chart-specific presentation path.
- Existing dashboard cache keys/invalidation behavior.
- Existing invoice and expense inclusion rules for monthly totals.

# Open Questions

None.
