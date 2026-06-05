## Overview

Add a shared `Rolling Year` period option and make it the default period when no valid period has been selected. The range is month-aligned: first day of the month 12 months before the current month through the last day of the current month.

## Problem

The current default period is `All time`, which makes dashboards and list surfaces start from an unbounded range. Users need the default period to show a recent, calendar-month-aligned rolling window while keeping all existing period choices available.

## Proposed Outcome

The shared period dropdown includes an option labeled exactly `Rolling Year`. For a user with no explicit `date_range` query parameter and no valid stored period selection, `Rolling Year` is selected by default and filters existing date-aware surfaces through the shared global date filter.

Assumption: The requested period dropdown is the shared global `date_range` dropdown rendered from `global_date_filter.options`, so this applies wherever that shared dropdown appears.

## Constraints / Non-Goals

- Do not add database migrations or data backfills.
- Do not change existing period option keys, labels, ordering semantics, or date bounds except for adding `Rolling Year` and changing the no-selection default.
- Do not override a valid explicit query-string selection or a valid persisted session selection.
- Do not redesign dashboard charts, list layouts, status filters, or saved filter behavior.
- Avoid new third-party date dependencies; implement month arithmetic with the standard library.

## Acceptance Criteria

### User Outcome

1. The shared period dropdown includes an option labeled exactly `Rolling Year`.
2. `Rolling Year` is selected by default for a fresh session/request with no valid `date_range` selection.
3. Existing period options remain selectable and continue to produce their current ranges.
4. Period labels shown in existing dashboard/list contexts reflect `Rolling Year` when that option is active.

### Technical Behavior

1. `rolling_year` starts on the first day of the month 12 months before the current month.
2. `rolling_year` ends on the last day of the current month.
3. For June 5, 2026, `rolling_year` resolves to June 1, 2025 through June 30, 2026.
4. `get_global_date_filter()` uses `rolling_year` as the fallback for missing or invalid stored selections.
5. Valid query-string and session selections for existing period keys remain honored.
6. Dashboard cache invalidation includes the new `rolling_year` key.

### Operations / Deployment

1. Deployment is code-only with no migration step.
2. Existing live sessions with valid selected periods continue to work.
3. Missing or invalid period state falls back to `Rolling Year` after deploy.
4. No generated databases, media, screenshots, videos, auth state, or static build output are committed.

### Validation

1. Unit tests cover `rolling_year` bounds, including the June 5, 2026 example and a year-boundary case.
2. View/context tests cover the default selected period and preservation of existing explicit period selections.
3. Existing tests that assumed `All time` as the default are updated to request `date_range=all` explicitly when that behavior is required.
4. The spec-declared demo and visual validation commands capture the reviewer-visible default period state.

## Implementation Plan

1. Update `invoices/utils/date_filters.py` with a stable `rolling_year` key, a default period constant, and standard-library month arithmetic for the rolling bounds.
2. Add `Rolling Year` to `get_date_range_options()` with label `Rolling Year` and generated `range_display`/summary metadata.
3. Change `get_global_date_filter()` fallback behavior from `all` to `rolling_year` without clobbering valid explicit or persisted selections.
4. Update dashboard cache invalidation in `invoices/views.py` so legacy dashboard cache keys for `rolling_year` are cleared.
5. Add focused date-filter tests and update affected dashboard/list tests that currently depend on implicit `All time`.
6. Add preview-safe Playwright evidence coverage for the default selected period.

## Task List

- [x] Add rolling-year date filter behavior
  - [x] Define a `rolling_year` period key and default date-range key in `invoices/utils/date_filters.py`.
  - [x] Implement month-aligned rolling bounds using standard-library date arithmetic.
  - [x] Add the `Rolling Year` option to the shared date range options.
  - [x] Update missing/invalid global period fallback behavior to use `rolling_year`.
  - [x] Add unit tests for option metadata, default behavior, and date-bound calculations.

- [x] Preserve shared UI and view behavior
  - [x] Verify existing templates that loop over `global_date_filter.options` render the new option without duplicate template logic.
  - [x] Update view tests that assumed `All time` by default to request `date_range=all` explicitly.
  - [x] Add view/context coverage that a fresh dashboard request selects `rolling_year`.
  - [x] Add coverage that existing explicit period options still filter as before.
  - [x] Include `rolling_year` in dashboard cache invalidation paths.

- [x] Add reviewer evidence capture for the default period
  - [x] Add a focused Playwright spec for the default `Rolling Year` period state.
  - [x] Add `./scripts/demo-evidence.sh rolling-year-period-default` as the repo-owned demo command.
  - [x] Add `./scripts/visual-validation.sh rolling-year-period-default` as a target-aware visual capture command using `OPENCODE_VISUAL_VALIDATION_TARGET=baseline|current`.
  - [x] Capture full-page screenshots of the relevant dashboard state and avoid relying on exact seeded row counts.

## Deployment / Rollout

- No migration or operator data action is required.
- Deploy with the normal application release path.
- Run targeted Django tests for date filters and affected invoice/dashboard views, then run `./scripts/ci.sh`.
- Run the spec-declared evidence commands in preview/review automation.
- After deploy, users with no stored period selection see `Rolling Year`; users with valid stored selections keep their selected period.

## File-Level Changes

### Add

- `invoices/tests/test_date_filters.py` for focused date-range helper coverage.
- `tests/e2e/rolling-year-period.spec.js` for reviewer-visible default-period evidence.
- `scripts/demo-evidence.sh` if not already present.
- `scripts/visual-validation.sh` if not already present.

### Modify

- `invoices/utils/date_filters.py` to add `rolling_year`, default fallback behavior, option metadata, and range summary support.
- `invoices/views.py` to include `rolling_year` in dashboard cache invalidation.
- `invoices/tests/test_invoices.py` to update expectations that currently assume `All time` is the implicit default.

### Keep

- Existing period dropdown templates unless stable evidence selectors are needed.
- Existing period option behavior for `this_month`, `last_month`, `ytd`, `last_year`, and `all`.
- Existing migrations, managed workflow files, generated assets, and runtime artifacts unchanged.

## Demo Media

### Scenario: rolling-year-period-default

#### Repo Command

./scripts/demo-evidence.sh rolling-year-period-default

#### Outputs

video + screenshots

#### Steps

1. Open the dashboard in an authenticated preview-safe session with no explicit `date_range` query parameter.
2. Let the page render the shared period dropdown in its default state.
3. Leave the dashboard visible with `Rolling Year` selected in the period control.

#### Screenshot Checkpoints

- dashboard-rolling-year-default: full-page screenshot of the dashboard with the period control showing `Rolling Year` as the selected period

## Visual Validation

### Identifier

rolling-year-period-default

### Capture Command

./scripts/visual-validation.sh rolling-year-period-default

### Steps

1. Open the dashboard in an authenticated preview-safe session with no explicit `date_range` query parameter.
2. In baseline mode, capture the stable pre-existing dashboard default period state without asserting PR-only controls.
3. In current mode, open the same dashboard state and verify the period control is using `Rolling Year` before capture.

### Full-Page Checkpoints

- dashboard-period-default: full-page screenshot of the dashboard with the period dropdown and KPI area visible

### Expected Comparisons

- The `dashboard-period-default` baseline/current pair should show the default selected period changing to `Rolling Year`.
- The surrounding dashboard layout and existing filter control placement should remain stable.

### Baseline SHA

`5c0022f697627c5e698058819209726a44d2ecb7`


## Open Questions

None.
