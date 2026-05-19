# Overview

Tighten the superuser-only `Recent backups` surface on `/backup-settings/` so the table is lighter to scan and the tabbed shell no longer carries the visible spacing defects shown in the issue screenshot. Keep this as a small presentation pass, not a backup workflow change.

# Problem

The current backup settings page still spends width and attention on information that is either redundant or better handled elsewhere:

- row status values are written out as full words inside a narrow table
- the `Error` column repeats failure context that is already available on the run detail page
- the tab shell has a visible detached seam/gutter at the left and right edges under the tabs
- the active panel adds more blank top space before the recent-backups card than the page needs

Together, those make the page feel heavier and more padded than requested.

# Proposed Outcome

Update only the recent-backups presentation on `/backup-settings/` so that:

- row status values render as compact success/failure indicators instead of written status words
- the `Error` column is removed from the table; failures continue to be inspectable through `View details`
- the tab strip and content container read as one connected surface with no blank side seam at the left or right edges
- the blank space between the tab strip and the first visible panel content is reduced to roughly half the current amount
- reviewer evidence explicitly reuses the existing backup-settings Playwright command with deterministic success and failure rows visible in preview-backed runs

Assumption: keep the `Status` column header text for scanability while replacing row values with icons, and render any rare `In progress` row with a compact neutral indicator plus accessible text rather than reintroducing a written status label.

# Constraints / Non-Goals

- Keep `/backup-settings/`, existing superuser gating, manual `Run backup now`, size downloads, and `backup_run_detail` behavior intact.
- Do not change backup execution, storage, scheduler behavior, retention logic, or backup data models.
- Do not redesign the `Backup settings` tab or the backup detail page beyond preserving access to failure information removed from the table.
- Scope spacing changes to the backup settings surface or otherwise keep other tabbed pages visually unchanged.
- Do not require local-only seeded data or manual shell mutation for reviewer evidence.

# Acceptance Criteria

## User Outcome

1. A superuser opening `Recent backups` sees compact status indicators instead of written `Succeeded` / `Failed` row values.
2. The `Error` column is not shown in the recent-backups table, and failure context remains reachable from `View details`.
3. The tab strip visually joins the recent-backups container with no detached blank gutter or exposed side-border notch at the left or right edges.
4. The visible blank space between the tab strip and the first recent-backups card is materially reduced to about half of the current layout.
5. Existing `Size` download links and `View details` actions remain available and usable.

## Technical Behavior

1. Existing superuser-only access, recent-run ordering, 10-row limit, compact datetime formatting, download flow, and run-detail routing remain unchanged.
2. Status indicators remain understandable without relying on color alone by preserving accessible status text or equivalent accessible naming for success, failure, and non-terminal states.
3. Removing the table `Error` column does not remove stored failure summaries or diagnostics from the underlying run record or detail page.
4. Any CSS or markup changes needed for the tab seam/padding issue are scoped so other tabbed pages do not regress.

## Operations / Deployment

1. No migrations, new environment variables, feature flags, or operator-only setup steps are required.
2. The standard deploy/build path remains sufficient for the template, CSS, seed-data, and test changes in this issue.
3. Preview-backed reviewer evidence uses the spec-declared Playwright command with deterministic recent-backup rows that visibly cover both success and failure states.

## Validation

1. Django tests cover status-indicator presentation metadata, absence of the `Error` column, and preserved detail/download behavior.
2. The reused Playwright scenario captures named reviewer evidence for the updated table and tab spacing using the committed repo command.
3. Separate visual validation captures the full recent-backups page so reviewers can compare the tighter tab/container spacing and changed table structure in context.

# Demo Media

Explicit reuse note: reuse is intentional from the existing `backup-settings-recent-backups-table` flow. Update and reuse `tests/e2e/backup-settings-tabs.spec.js` with the same repo command below; do not rely on the current checkpoints without adding the issue-specific states below.

### Scenario: backup-settings-recent-backups-table

#### Repo Command

`./scripts/e2e.sh tests/e2e/backup-settings-tabs.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Reach `/backup-settings/` through the repo-owned smoke-user flow with deterministic recent-backup rows that include at least one successful downloadable run and one failed run.
2. Leave `Recent backups` active and confirm the table shows compact status indicators, no visible `Error` column, and the existing `Size` / `View details` actions.
3. Confirm the tab strip and recent-backups container read as one connected surface, with the top gap before the first card visibly tighter than the current baseline.
4. Open one populated `Size` link and confirm it still opens in a new tab/window without navigating away from `/backup-settings/`.
5. Use `View details` for a failed run and confirm the detail page still exposes the run-specific diagnostics that were removed from the table.

#### Screenshot Checkpoints

- `backup-settings-recent-backups-tab-surface`
- `backup-settings-recent-backups-table`
- `backup-run-detail-from-table`

# Visual Validation

Explicit reuse note: reuse the existing backup-settings visual capture command from the current Playwright path; update the full-page checkpoint expectations for this issue rather than inventing a local-only manual capture.

### Identifier

backup-settings-recent-backups-ux-polish

### Capture Command

`./scripts/e2e.sh tests/e2e/backup-settings-tabs.spec.js`

### Steps

1. Reach `/backup-settings/` through the same deterministic smoke-data path used by the demo scenario and keep `Recent backups` selected.
2. Wait for the page shell and table to settle, with both a success row and a failure row visible on the page.
3. Capture the full page in that state.

### Full-Page Checkpoints

- `backup-settings-recent-backups-table-full-page`

### Expected Comparison Notes

- Reviewers should see the same backup settings page shell and tab order, but the recent-backups table should no longer show an `Error` column.
- Success and failure rows should be distinguishable with compact status indicators instead of written status words.
- The tab strip should visually connect to the surrounding recent-backups surface without the current detached left/right gutter or notch.
- The blank space between the tab strip and the first visible recent-backups card should be visibly smaller than the current baseline.

### Baseline SHA

`130cbd69fa1ad832126ba28a28ec38c61499577e`


# Implementation Plan

1. Extend the recent-backups presentation preparation in `invoices/views.py` so each run exposes compact, accessible status-indicator metadata alongside existing datetime and download metadata.
2. Update `invoices/templates/invoices/backup_settings.html` to remove the `Error` column, render status cells as compact Tabler-based indicators with accessible text, and keep failure drill-down on `View details`.
3. Add backup-settings-specific classes or modifiers in the template/CSS so the tab/container seam is closed and the active-panel top spacing is halved without regressing other tabbed pages that share `.tab-nav` / `.tab-panel`.
4. Extend deterministic E2E seed data with at least one failed run and update Django/Playwright coverage plus the issue-specific demo and visual checkpoints.

# Task List

- [x] Add recent-backups status presentation metadata
  - [x] Extend `_prepare_recent_backup_runs` with status-indicator metadata that the template can render without written row-status words.
  - [x] Keep existing datetime formatting and download-link preparation unchanged while covering success, failure, and non-terminal states in Django tests.

- [x] Update the Recent backups table and spacing UI
  - [x] Remove the `Error` column from `backup_settings.html` and keep failure context discoverable through `View details`.
  - [x] Render the status cell with compact Tabler icon treatment plus accessible non-visual text or equivalent accessible naming.
  - [x] Add backup-settings-specific markup/CSS hooks to remove the tab/container side seam and reduce the panel's top gap to roughly half the current spacing.
  - [x] Update render assertions for the changed table structure and scoped spacing hooks.

- [x] Make reviewer evidence deterministic and issue-specific
  - [x] Update `seed_e2e_smoke.py` so preview-backed evidence includes both successful and failed recent-backup rows while preserving at least one downloadable artifact row.
  - [x] Explicitly reuse `tests/e2e/backup-settings-tabs.spec.js` for this issue’s recent-backups scenario and add assertions/checkpoints for icon status, removed `Error` column, and tighter tab spacing.

# Deployment / Rollout

This is a low-risk template/CSS/presentation rollout with no schema or backup-process impact.

1. Deploy through the normal application release path.
2. No migration or environment update step is expected.
3. Before merge/release, rely on the repo-owned Django and Playwright validation named above rather than manual local-only screenshot steps.
4. After deploy, verify as a superuser that `/backup-settings/` still opens on `Recent backups`, size links still open separately, failed runs still reach diagnostics through `View details`, and the tighter tab spacing renders correctly in the live shell.

# File-Level Changes

## Add

- None.

## Modify

- `invoices/templates/invoices/backup_settings.html` — remove the `Error` column, render compact accessible status indicators, and add backup-settings-specific hooks for the tab surface spacing changes.
- `invoices/views.py` — extend recent-backup presentation data with status-indicator metadata while preserving existing datetime/download preparation.
- `invoices/static/invoices/css/design/components.css` — add scoped backup-settings spacing rules for the tab seam and reduced panel top gap.
- `invoices/tests/test_backups.py` — update render/helper assertions for status indicators, removed `Error` column, and preserved detail/download behavior.
- `invoices/management/commands/seed_e2e_smoke.py` — seed deterministic recent-backup rows that visibly cover both success and failure in preview-backed runs.
- `tests/e2e/backup-settings-tabs.spec.js` — explicitly reuse and update the existing backup settings Playwright scenario with issue-specific checkpoints and assertions.

## Keep

- `invoices/templates/invoices/backup_run_detail.html` — keep the detail page as the place where failure diagnostics and error summaries remain visible.
- `invoices/static/invoices/js/backup_settings.js` — keep existing tab-switching behavior; no interaction-model change is required.
- `invoices/urls.py` and `invoices/services/backups.py` — keep the existing recent-backups routes and download behavior unchanged.
- Existing backup models and migrations — no schema change is expected.
- `scripts/e2e.sh`, `scripts/preview.sh`, and `playwright.config.js` — reuse the current managed Playwright/preview flow.

# Open Questions

None.
