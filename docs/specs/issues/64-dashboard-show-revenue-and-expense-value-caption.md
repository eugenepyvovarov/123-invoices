# Overview

Update the dashboard monthly revenue vs expense chart so amount captions appear only on hover, with separate captions for the blue revenue area and the orange expense overlay area of each monthly bar.

# Problem

The chart currently exposes monthly values through accessible text and a single rotated visible label, but it does not let users inspect revenue and expense values independently without adding persistent label clutter. The latest requirement narrows the interaction: captions should appear only when the user hovers the specific chart segment they want to inspect.

# Proposed Outcome

Replace the current single always-visible total label treatment with hover-triggered per-segment captions:

- hovering the blue revenue portion of a monthly bar reveals the revenue amount
- hovering the orange expense overlay portion reveals the expense amount

The chart keeps the current single-bar-with-expense-overlay model, month/year axis labels, and blue/orange semantics. Captions remain concise, use two-decimal currency formatting, and do not stay visible when the pointer leaves the segment.

# Constraints / Non-Goals

- Do not change the current shared-bar chart model or split bars into separate columns.
- Do not change the 24-month range, chart title, legend semantics, or month/year axis labels.
- Do not restore persistent visible captions across all bars.
- Do not add a new chart library or JavaScript-driven tooltip system unless the existing template/CSS approach cannot support segment-specific hover behavior.
- Do not remove the existing accessible text that exposes invoiced and expense values.
- All displayed monetary values must use consistent two-decimal formatting.

# Acceptance Criteria

## User Outcome

1. Hovering the blue revenue area of a monthly bar shows the revenue amount for that month.
2. Hovering the orange expense area of a monthly bar shows the expense amount for that month.
3. Revenue and expense captions are not persistently visible when the chart is idle.
4. Month/year axis labels remain visible and unchanged.

## Technical Behavior

1. The chart continues to render as one monthly revenue bar with an expense overlay inside it.
2. Revenue hover captions are tied to the revenue segment, and expense hover captions are tied to the expense overlay segment rather than to the whole bar indiscriminately.
3. Hover caption values are sourced from the same monthly invoiced and expense totals already used by the chart.
4. Hover captions use consistent two-decimal currency formatting.
5. The previous rotated single total label is removed or superseded so the rendered hover behavior reflects separate revenue and expense values.
6. Existing visually hidden month-level descriptive text remains present for screen readers.

## Operations / Deployment

1. The change requires no database migration, background job, or feature flag.
2. The shared chart partial continues to work for both the company dashboard and the cross-company dashboard.
3. The hover interaction does not reintroduce unreadable overlap or persistent clutter across the current dashboard range.

## Validation

1. Regression coverage verifies the chart context or rendered markup needed for hover captions.
2. Tests verify the rendered chart exposes separate revenue and expense caption elements or attributes for a month with both values present.
3. Tests continue to verify accessible month text and shared chart behavior where applicable.

# Implementation Plan

1. Remove reliance on the current single `data-value-label` total label for dashboard bars.
2. Expose separate revenue and expense display strings in the chart data only if the existing `invoiced_display` and `expense_display` fields are insufficient for clean template rendering.
3. Update the shared dashboard chart partial so each monthly bar contains distinct caption elements and hover targets for:
   - the revenue area
   - the expense overlay area
4. Update chart CSS so captions are hidden by default and become visible only for the hovered segment, while keeping caption placement readable and visually associated with the hovered area.
5. Preserve existing screen-reader text and month-level aria labeling.
6. Extend dashboard tests to cover the new markup contract and removal of the old single total label treatment.

# Task List

- [x] Update chart data and markup contract
  - [x] Remove the old single total label dependency from dashboard bar rendering.
  - [x] Keep or expose separate revenue and expense display values in `_build_dashboard_chart`.
  - [x] Update the shared chart partial to render distinct revenue and expense caption elements per month.

- [x] Implement hover-only segment captions
  - [x] Add a revenue hover target and caption tied to the blue portion of each bar.
  - [x] Add an expense hover target and caption tied to the orange overlay portion of each bar.
  - [x] Remove the old rotated single-label styling and replace it with hidden-by-default hover caption styles.

- [x] Validate shared dashboard behavior
  - [x] Add or update tests asserting separate revenue and expense caption markup for a month with both values.
  - [x] Add or update tests asserting the old single `data-value-label` output is no longer the rendered contract.
  - [x] Run the relevant dashboard tests and the full Django test suite.

# Deployment / Rollout

This is a template/CSS change with at most a small chart-context adjustment. No migration or staged rollout is needed. Before release, verify in a browser that hovering the blue segment reveals revenue, hovering the orange segment reveals expenses, and idle chart state remains uncluttered across representative low and high values.

# File-Level Changes

## Modify

- `invoices/templates/invoices/partials/dashboard_chart.html` — replace the single total-label output with separate revenue and expense hover caption markup.
- `invoices/static/invoices/css/base.css` — remove the old rotated label treatment and add hidden-by-default hover caption styling for revenue and expense segments.
- `invoices/views.py` — keep or refine chart context fields used to render separate hover captions cleanly.
- `invoices/tests/test_invoices.py` — update dashboard chart regression coverage for hover-caption markup and accessible text preservation.

## Keep

- `invoices/templates/invoices/dashboard.html` — continue including the shared dashboard chart partial.
- `invoices/templates/invoices/cross_company_dashboard.html` — continue including the shared dashboard chart partial.
- Current chart title, legend, month/year axis labels, and blue/orange chart semantics.

# Open Questions

None.
