# Overview

Refine only the `Recent backups` tab on `/backup-settings/` so the history table is easier to scan and its row actions match the rest of the app, without changing backup execution or the backup-details workflow.

# Problem

The current history table is visually heavy:

- `Started` and `Finished` use longer 12-hour timestamps than the page needs.
- The `Object key` column takes significant width for data that is mainly useful in the detail view.
- `View details` is rendered as a plain text link instead of a table action button.
- The requested size-download behavior has no current app-side path.

That combination makes the table harder to read and less consistent than other action-driven tables in the app.

# Proposed Outcome

Keep the existing tabbed `/backup-settings/` page and recent-run data source, but update the `Recent backups` table so that:

- `Started` and `Finished` render as compact local datetimes in 24-hour format with minutes and no `am/pm`.
- The year is suppressed for repeated visible rows and only shown again when the displayed sequence crosses into a different year.
- `Object key` is removed from the table; the backup details page remains the place to inspect the full key.
- Each populated `Size` value becomes a new-tab download affordance backed by a superuser-only app route that generates a fresh short-lived download target when clicked.
- `View details` stays in the Actions column, but uses the existing compact action-button treatment already used elsewhere in the UI.
- Reviewer evidence explicitly reuses the existing backup settings Playwright command, with deterministic recent-backup rows available in preview-backed runs so the same command can prove the formatting and action changes.

Assumption: apply the year-suppression rule independently within the `Started` and `Finished` columns, because they are presented as separate top-to-bottom date sequences.

# Constraints / Non-Goals

- Keep `/backup-settings/`, existing superuser gating, the manual `Run backup now` flow, and the `backup_run_detail` page intact.
- Do not change backup execution, retention logic, scheduler behavior, or `BackupRun` persistence.
- Do not expose S3 credentials or rely on long-lived external object URLs embedded in the page.
- Do not add migrations, feature flags, restore/import behavior, or a broader backup-settings redesign.
- Do not change backup detail-page formatting unless required to keep the table-to-details flow working.

# Acceptance Criteria

## User Outcome

1. A superuser opening `Recent backups` sees shorter `Started` and `Finished` values rendered in 24-hour time with minutes and no `am/pm`.
2. Repeated years are not shown on every row; the year only reappears when the visible descending date sequence crosses into a different year.
3. The `Object key` column is no longer shown in the `Recent backups` table.
4. For rows with a downloadable backup artifact, the visible `Size` value is a link that opens the download flow in a new tab/window.
5. `View details` remains available per row and is rendered as a button-style action consistent with other table actions in the app.
6. The table remains easy to scan on desktop and the existing backup-details flow remains reachable from the table.

## Technical Behavior

1. Existing `/backup-settings/`, `backup_run_detail`, and `Run backup now` permissions and behavior remain unchanged.
2. The new size-link flow is produced server-side through a superuser-only route that can issue a fresh download target at click time rather than embedding long-lived object URLs in the rendered table.
3. Rows missing download metadata do not render broken download anchors and continue to fall back to the existing placeholder treatment.
4. Recent-backup ordering and the current 10-row limit remain unchanged.
5. The table keeps the current timezone/localtime behavior; only the display format changes.

## Operations / Deployment

1. The change ships without migrations, scheduler changes, or new required environment variables.
2. Preview-backed reviewer evidence uses the spec-declared Playwright command and deterministic repo-owned smoke data that can show both same-year and cross-year rows.
3. The normal deploy/build path remains sufficient for the template, view, service, and test changes in this issue.

## Validation

1. Django tests cover compact datetime rendering, year suppression, removed-column output, size-link download routing, unchanged superuser-only access, and unchanged details/manual-backup behavior.
2. The spec-declared Playwright scenario captures reviewer evidence for the updated recent-backups table, including compact datetimes, linked size values, and the styled `View details` action.
3. A separate visual-validation capture shows the full-page table state after the column and action changes so reviewers can compare the layout safely in preview.

# Demo Media

Explicit reuse note: reuse is intentional for this issue. Update and reuse `tests/e2e/backup-settings-tabs.spec.js`; do not rely on its current checkpoints without adding the states below.

### Scenario: backup-settings-recent-backups-table

#### Repo Command

`./scripts/e2e.sh tests/e2e/backup-settings-tabs.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Reach `/backup-settings/` through the repo-owned smoke-user Playwright flow with deterministic recent-backup rows available in both local and preview-backed runs.
2. Keep `Recent backups` active and confirm the table shows compact `Started` and `Finished` values in 24-hour time, with a visible year-transition row where the year is reintroduced.
3. Confirm `Object key` is absent, populated `Size` values read as download links, and `View details` is rendered as a button-style action.
4. Open one populated size link and confirm it opens in a new tab/window while the original tab remains on the recent-backups table.
5. Use `View details` for one row and confirm the backup-details page still opens.

#### Screenshot Checkpoints

- `backup-settings-recent-backups-table`
- `backup-settings-recent-backups-actions`
- `backup-run-detail-from-table`

# Visual Validation

Reuse note: use the same command as Demo Media after updating the scenario with the issue-specific checkpoints below.

### Identifier

backup-settings-recent-backups-table-layout

### Capture Command

`./scripts/e2e.sh tests/e2e/backup-settings-tabs.spec.js`

### Steps

1. Reach `/backup-settings/` through the same deterministic smoke-data path used by the demo scenario and leave `Recent backups` selected.
2. Capture the full page in that state so reviewers can compare the overall page layout, recent-backups table area, and the changed row-action treatment in context.

### Full-Page Checkpoints

- `backup-settings-recent-backups-table-full-page`

### Expected Comparisons

- Reviewers should see the `Recent backups` page captured in full-page context, preserving the existing page shell and tabbed layout while the recent-backups area reflects the issue’s table/action changes.
- When backup rows are present in the current screenshot, reviewers should see more compact `Started` / `Finished` formatting, no visible `Object key` column, linked `Size` values, and `View details` presented as a compact action button rather than a plain inline link.

### Baseline SHA

`33a22ae2ef56acd4b8854f68080573d610ae4424`


# Implementation Plan

1. Add a server-side recent-backups presentation helper in the backup settings flow so each row has compact display strings, per-column year-suppression decisions, and download-link availability.
2. Add a superuser-only backup-download view/route under the backup settings namespace that generates a fresh short-lived download target from the stored object key and redirects the new tab there.
3. Update `invoices/templates/invoices/backup_settings.html` to remove `Object key`, render the compact datetime values, turn populated size values into links, and restyle `View details` with the existing compact table-action button treatment.
4. Move deterministic recent-backup demo data into the repo-owned smoke/preview seeding path so preview-backed Playwright evidence can show the required formatting states without local-only `manage.py shell` mutations.
5. Extend Django and Playwright coverage around formatting, permissions, link behavior, details navigation, and the new reviewer-evidence checkpoints.

# Task List

- [x] Add recent-backups presentation and download behavior
  - [x] Add a helper path that prepares compact `Started` and `Finished` display values and tracks when each column should reintroduce the year.
  - [x] Add a superuser-only backup download endpoint that issues a fresh download target from a stored backup object key.
  - [x] Cover the download endpoint’s permissions and redirect behavior in Django tests.

- [x] Update the Recent backups table UI
  - [x] Remove the `Object key` column from `backup_settings.html`.
  - [x] Render populated `Size` values as new-tab download links and keep placeholder behavior for rows without download data.
  - [x] Restyle `View details` with the existing compact table-action button treatment and tighten table readability where needed for desktop scanning.
  - [x] Add or update Django render assertions for the compact datetime output and the changed table structure.

- [x] Make reviewer evidence preview-safe and issue-specific
  - [x] Extend the repo-owned smoke data so recent-backup rows exist in preview-backed runs and include same-year plus cross-year examples.
  - [x] Explicitly update and reuse `tests/e2e/backup-settings-tabs.spec.js` for this issue’s recent-backups scenario.
  - [x] Capture the named demo checkpoints and full-page visual-validation checkpoints from the same command.

- [x] Validate rollout safety
  - [x] Run targeted backup Django tests covering the changed table and download flow.
  - [x] Run the spec-declared Playwright command and confirm it emits the required screenshots and video.
  - [x] Smoke-check `/backup-settings/` as a superuser after deployment to confirm the table changes and unchanged detail navigation.

# Deployment / Rollout

This is a low-risk view/template/service rollout with no schema or scheduler impact.

1. Deploy through the normal application release path.
2. Let the standard build flow publish any template changes; no extra migration step is expected.
3. After deploy, verify as a superuser that `/backup-settings/` still opens on `Recent backups`, size links open a new tab/window, and `View details` still reaches the existing run details page.
4. Confirm the implementation PR’s demo and visual evidence both use the spec-declared Playwright command and include the named checkpoints.

# File-Level Changes

## Add

- None.

## Modify

- `invoices/templates/invoices/backup_settings.html` — remove the `Object key` column, render compact datetimes, link the `Size` cells, and restyle the row action.
- `invoices/views.py` — prepare recent-backup row presentation data and add the superuser-only download route behavior.
- `invoices/urls.py` — add the backup download route under the existing backup-settings namespace.
- `invoices/services/backups.py` — add a helper that can generate a fresh backup download target from the stored object key.
- `invoices/tests/test_backups.py` — cover formatting output, removed-column rendering, download routing, permissions, and unchanged details/manual-run behavior.
- `invoices/management/commands/seed_e2e_smoke.py` — seed deterministic recent-backup rows suitable for preview-backed reviewer evidence.
- `tests/e2e/backup-settings-tabs.spec.js` — explicitly reuse and update the backup settings Playwright scenario for the recent-backups table evidence and new checkpoints.

## Keep

- `invoices/templates/invoices/backup_run_detail.html` — keep the existing detail page as the drill-down surface for full object-key and diagnostic information.
- `invoices/static/invoices/js/backup_settings.js` — no settings-tab interaction change is required for this table-focused issue.
- `invoices/models.py` and existing backup migrations — no schema change is expected.
- `playwright.config.js`, `scripts/e2e.sh`, and `scripts/preview.sh` — reuse the current managed Playwright and preview flow once the smoke seed data includes the required backup rows.

# Open Questions

None.
