# Overview

Fix the dashboard `Revenue vs Expense` chart so the visual geometry matches the underlying numbers. Replace the capped overlay model with two side-by-side monthly bars on one shared absolute y-scale, add visible chart axes, and make the blue/orange legend pills interactive so revenue and expense can be shown or hidden independently without changing scale semantics.

# Problem

The current chart is misleading because expense is not rendered as an independent value on the same scale as revenue.

Repository context matches the reported root cause:

- `invoices/views.py` computes `expense_overlay_total = min(expense_total, invoiced_total)`
- `invoices/templates/invoices/partials/dashboard_chart.html` renders the orange expense bar inside the blue revenue bar container
- the current chart styling treats expense as an overlay instead of a separate comparable series

That causes false comparisons:

- expense can never appear taller than revenue in the same month
- a larger expense can appear smaller than a lower revenue value in another month
- users cannot read chart scale or month labels without hover
- the legend is not interactive even though this issue now requires show/hide controls

The attached live screenshots show the current distortion on real dashboard data.

# Proposed Outcome

Rebuild the shared dashboard chart so each month renders:

- one blue revenue bar
- one orange expense bar
- both bars side by side within the same month slot
- both heights derived from their real values against one shared absolute chart maximum

The refreshed chart should also:

- show visible horizontal guide lines across the plot area
- show left-side y-axis value labels
- show month labels under the chart without hover
- render the revenue and expense legend pills as clickable controls that independently show or hide each series
- keep at least one series visible at all times
- preserve the same shared y-scale and axis labels while toggling either series
- preserve correct accessible text for month, revenue, and expense values

# Demo Scenario

## Scenario ID

`dashboard-chart-shared-scale-toggles`

## Command

`npx playwright test tests/e2e/dashboard-chart-shared-scale-toggles.spec.js`

## Steps

1. Log in with the repo-owned Playwright dashboard user.
2. Open the dashboard for a seeded company that includes at least one month where `expense_total > invoiced_total`.
3. Confirm the `Revenue vs Expense` chart shows visible horizontal guide lines, left-side value labels, month labels, and two clickable legend pills for Revenue and Expenses.
4. Locate a month where expenses exceed revenue and verify the orange bar is visibly taller than the blue bar for that month.
5. Verify each month renders two separate side-by-side bars rather than an orange overlay inside a blue bar.
6. Click the Expenses legend pill and verify the orange series hides while revenue stays visible, with the y-axis labels and guide lines unchanged.
7. Click the Expenses legend pill again to restore the orange series.
8. Click the Revenue legend pill and verify the blue series hides while expenses stay visible, with the y-axis labels and guide lines unchanged.
9. Attempt to hide the final remaining visible series and verify the chart does not enter a fully hidden state.
10. If the seeded dataset requires switching companies first, perform that switch explicitly in the scenario.

## Screenshot Checkpoints

- `chart-default-state-with-axes-and-toggles`
- `chart-expense-exceeds-revenue`
- `chart-expenses-hidden-stable-scale`
- `chart-revenue-hidden-stable-scale`

Reuse is not implicit. This issue requires a new or explicitly updated Playwright scenario for the shared-scale chart with interactive legend toggles; implementation should not assume an older dashboard scenario applies unless this command is the one being reused.

# Constraints / Non-Goals

- Do not keep any geometry that caps expense height to revenue height.
- Do not preserve the overlay-inside-revenue rendering model.
- Do not recalculate the y-axis scale when a series is toggled off.
- Do not allow both series to become hidden at the same time.
- Do not add extra chart interactions beyond the required legend toggles and normal hover/accessibility behavior.
- Do not add a new charting library.
- Do not change KPI calculations, date filtering rules, or invoice/expense aggregation semantics beyond the chart data needed for truthful rendering.
- Keep monetary values displayed with two decimal places.
- Keep the chart partial shared by `dashboard.html` and `cross_company_dashboard.html`.
- Continue using Charts.css-compatible structure for chart rendering.
- Implement the legend controls using the repository’s existing accessible grouped-button pattern rather than a custom one-off control.

# Acceptance Criteria

## User Outcome

1. Each month renders separate revenue and expense bars side by side within the same month slot.
2. Revenue and expense heights are visually comparable on one shared absolute y-scale.
3. In a month where `expense_total > invoiced_total`, the orange expense bar can visibly exceed the blue revenue bar.
4. Users can read chart scale and months without hover through visible guide lines, left-side value labels, and month labels under the chart.
5. The legend pills are clickable and let users show or hide revenue and expense independently.
6. The chart never ends in a fully hidden state.

## Technical Behavior

1. The dashboard chart data no longer includes or depends on `expense_overlay_total` for rendering.
2. Revenue and expense sizing are both derived from their uncapped monthly totals against the same chart maximum.
3. The chart markup no longer renders the orange series as an absolutely positioned overlay inside the blue bar container.
4. Toggling a legend pill changes series visibility only; it does not change the chart maximum, y-axis labels, or guide-line positions.
5. Legend controls expose accessible toggle state, including the state where the final visible series cannot be turned off.
6. The shared chart partial renders correctly in both the single-company dashboard and the cross-company dashboard.

## Operations / Deployment

1. The change ships as code, template, static asset, and test updates only and requires no schema migration.
2. Static asset collection and dashboard rendering continue to work after deployment.
3. Post-deploy verification includes a dataset with at least one month where expenses exceed revenue and confirms the bar geometry is no longer capped by revenue.
4. Post-deploy verification confirms the legend toggles work, scale labels remain stable while toggling, and the chart cannot be fully hidden.

## Validation

1. Automated Django coverage includes a month where `expense_total > invoiced_total` and verifies the rendered sizing data is no longer capped to revenue.
2. Automated rendering coverage verifies separate side-by-side series markup, visible y-axis labels, visible month labels, and legend toggle state markup.
3. Existing tests that encode overlay-era behavior are replaced rather than extended.
4. Automated front-end coverage validates the defined Playwright demo scenario, including stable-scale toggling and the guard against hiding both series.

# Implementation Plan

1. Replace the chart data contract so monthly revenue and expense totals remain uncapped and the chart exposes shared-axis tick data derived from the full visible dataset baseline.
2. Rebuild the shared chart partial to render paired monthly bars, visible axes, and legend pills as accessible toggle controls.
3. Add chart interaction logic that toggles series visibility client-side while preserving a fixed y-scale and preventing the fully hidden state.
4. Replace overlay-specific styling and tests with coverage for side-by-side rendering, stable toggling, and visible axis labels.

# Task List

- [x] Replace the chart data contract
  - [x] Remove `expense_overlay_total` from `_build_dashboard_chart` in `invoices/views.py`.
  - [x] Compute the shared chart maximum from uncapped revenue and expense totals.
  - [x] Add chart tick and label metadata for visible left-side axis labels and guide lines.

- [x] Rebuild the shared chart markup
  - [x] Update `invoices/templates/invoices/partials/dashboard_chart.html` to render separate side-by-side revenue and expense bars for each month.
  - [x] Add visible horizontal guide lines, left-side value labels, and month labels to the chart structure.
  - [x] Replace the static legend copy with accessible revenue and expense toggle buttons using grouped-button markup.

- [x] Add chart toggle behavior and styling
  - [x] Add a dedicated dashboard chart script to toggle revenue and expense visibility without recomputing the shared scale.
  - [x] Prevent the last visible series from being toggled off and expose the correct disabled or inert state in the UI.
  - [x] Update chart CSS for paired bars, axis labels, guide lines, and toggle-pill states for visible, hidden, and locked-last-series behavior.
  - [x] Load the chart script on both dashboard entry points that include the shared chart partial.

- [x] Replace regression coverage
  - [x] Remove overlay-era assertions from `invoices/tests/test_invoices.py` and add shared-scale assertions for uncapped expense rendering.
  - [x] Add server-rendered assertions for axis labels, month labels, and legend toggle state markup.
  - [x] Add `tests/e2e/dashboard-chart-shared-scale-toggles.spec.js` for the demo scenario, including stable-scale toggle checks.

# Deployment / Rollout

1. No migration or data backfill is required.
2. Run targeted Django tests and the chart Playwright scenario before release.
3. Run static asset collection as part of normal deployment validation.
4. After deployment, verify the chart on a company dataset where expenses exceed revenue and confirm side-by-side bars, stable axes, legend toggles, and the non-empty visible-state guard all behave correctly.

# File-Level Changes

## Add

- `invoices/static/invoices/js/dashboard_chart.js` — client-side legend toggle behavior for series visibility with stable scale semantics.
- `tests/e2e/dashboard-chart-shared-scale-toggles.spec.js` — Playwright regression for the shared-scale chart and toggle behavior.

## Modify

- `invoices/views.py` — remove capped overlay sizing and expose shared-scale chart metadata.
- `invoices/templates/invoices/partials/dashboard_chart.html` — render side-by-side series, visible axes, month labels, and interactive legend controls.
- `invoices/static/invoices/css/base.css` — replace overlay chart styles with paired-bar, axis, and toggle styles.
- `invoices/templates/invoices/dashboard.html` — load the dashboard chart script for the single-company dashboard.
- `invoices/templates/invoices/cross_company_dashboard.html` — load the dashboard chart script for the cross-company dashboard.
- `invoices/tests/test_invoices.py` — replace overlay-era chart assertions with shared-scale and toggle markup assertions.

## Keep

- `invoices/templates/invoices/dashboard.html` and `invoices/templates/invoices/cross_company_dashboard.html` as the two entry points that continue to include the shared chart partial.
- Existing KPI cards, date-range filtering, and non-chart dashboard business logic.
- Existing Playwright auth and company-switching helpers for dashboard access.

# Open Questions

None.
