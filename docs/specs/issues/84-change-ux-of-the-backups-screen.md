# Overview

Rework the superuser-only backup settings page into a tabbed layout so recent backup history is the primary landing view and the immediate backup action sits with that history instead of in a separate top block.

# Problem

The current page mixes status summary, manual backup execution, settings editing, and recent history in one long screen. The `Run backup now` action lives in a standalone first block above the actual history table, which makes the page harder to scan and separates the action from the runs it affects.

The requested UX is narrower and clearer:

- remove the current first summary/run block
- move `Run backup now` into the recent-history area on the right side
- split the page into two tabs
- keep one tab focused on recent backups and one tab focused on backup settings

# Proposed Outcome

Implement `/backup-settings/` as a two-tab page in this order:

- `Recent backups`
- `Backup settings`

Recommended cut:

- make `Recent backups` the default active tab
- keep the existing recent backup table and detail links inside `Recent backups`
- move the existing dedicated `Run backup now` POST action into the `Recent backups` header/right side
- keep visible helper copy near that action that it uses saved settings, not unsaved form edits
- move `Destination`, `Schedule and retention`, `Test S3 connection`, and `Save changes` into the `Backup settings` tab
- remove the current standalone first block rather than rebuilding it as a third summary surface
- reuse the repository’s existing tab-nav/tab-panel pattern so tab switching stays in-page and does not discard unsaved form input

# Constraints / Non-Goals

- Keep the page and manual backup action superuser-only.
- Do not change backup execution behavior, scheduler logic, retention logic, or `BackupRun` history semantics.
- Do not merge `Run backup now` into the settings form; it must remain a separate POST action.
- Do not change the existing `backup_run_now`, save-settings, or test-S3 endpoints.
- Do not add migrations, feature flags, or a third backup-summary panel.
- Do not assume the older `sidebar-backups-account-action` Playwright scenario is sufficient for this issue; demo reuse must be explicit.

# Acceptance Criteria

## User Outcome

1. A superuser opening `/backup-settings/` sees two tabs in this order: `Recent backups`, then `Backup settings`.
2. `Recent backups` is the default visible tab and shows the recent backup history table.
3. The `Run backup now` action appears on the right side of the `Recent backups` view instead of in the old standalone first block.
4. The `Backup settings` tab shows the existing `Destination` and `Schedule and retention` sections plus `Test S3 connection` and `Save changes`.
5. The page no longer renders the old standalone first summary/run block as a separate top section.

## Technical Behavior

1. Existing superuser gating for the page, recent-run detail view, and manual run action remains unchanged.
2. The relocated `Run backup now` control still submits to the dedicated `backup_run_now` POST endpoint and does not submit the settings form.
3. The helper copy near `Run backup now` still makes clear that unsaved form edits are not used.
4. Tab switching stays in-page and does not trigger form submission or clear unsaved settings input.
5. The recent history view continues to show the latest 10 `BackupRun` records with existing status/detail behavior.

## Operations / Deployment

1. The change ships without migrations, scheduler reconfiguration, or environment changes.
2. The implementation PR remains compatible with the managed demo-evidence workflow by using only the spec-declared Playwright command.
3. Rollout follows the normal deploy path for template/test changes, with existing build and collectstatic flow remaining sufficient if static assets are touched.

## Validation

1. Django render tests verify the two-tab layout, default `Recent backups` state, relocated `Run backup now` action, and absence of the removed first block.
2. Django tests verify the settings form and `Test S3 connection` behavior still work after moving those controls under `Backup settings`.
3. Existing manual-run tests continue to verify that `Run backup now` uses persisted settings rather than unsaved page edits.
4. A Playwright scenario verifies superuser navigation to the backup settings page, the visible tab structure, the default recent-backups state, and the backup-settings tab content with the named screenshot checkpoints.

# Demo Scenario

**Source-of-truth note:** Reuse is not implicit for this issue. Do not rely on `sidebar-backups-account-action` unless this spec is explicitly updated to point to it. Use the scenario below for demo evidence.

- **Scenario ID:** `backup-settings-tabs`
- **Command:** `./scripts/e2e.sh tests/e2e/backup-settings-tabs.spec.js`
- **User-visible steps:**
  1. Seed the repo-owned E2E data and open the app with the standard Playwright login flow.
  2. Use the repo-owned smoke setup to reach the superuser-only backup settings page.
  3. Confirm `Recent backups` and `Backup settings` tabs are visible, with `Recent backups` selected by default.
  4. Confirm the `Recent backups` view shows the history table and the `Run backup now` action on the right side, with no standalone first summary/run block above the tabs.
  5. Switch to `Backup settings` and confirm `Destination`, `Schedule and retention`, `Test S3 connection`, and `Save changes` are visible there.
- **Screenshot checkpoints:**
  - `backup-settings-tabs`
  - `backup-settings-recent-backups-run-now`
  - `backup-settings-backup-settings-tab`
- **Recorded evidence:**
  - The same spec-declared command must be the path used by the managed demo workflow to attach the scenario video and named screenshots to the implementation PR.

# Implementation Plan

1. Restructure `invoices/templates/invoices/backup_settings.html` around two tab panels using the existing tab-nav/tab-panel pattern.
2. Move the recent history area into the default `Recent backups` tab and rename the visible section copy from `Recent runs` to `Recent backups`.
3. Relocate the existing `Run backup now` form into the `Recent backups` header/right side while preserving its dedicated POST target and saved-settings warning copy.
4. Move the settings form sections and footer actions into the `Backup settings` tab without changing save or S3-test behavior.
5. Extend Django backup tests for the new layout and add the spec-bound Playwright scenario for demo evidence.

# Task List

- [x] Build the two-tab backup settings shell
  - [x] Add `Recent backups` and `Backup settings` tab triggers and panels to `backup_settings.html` using the existing tab pattern.
  - [x] Make `Recent backups` the default active panel.
  - [x] Remove the old standalone first summary/run block from the page layout.
  - [x] Update backup settings render tests to assert the tab labels and absence of the removed top block.

- [x] Move recent history and manual backup controls into `Recent backups`
  - [x] Rename the visible history section from `Recent runs` to `Recent backups`.
  - [x] Keep the existing recent backup table and per-run detail links inside the `Recent backups` panel.
  - [x] Move the dedicated `Run backup now` POST form into the `Recent backups` header/right side.
  - [x] Extend backup view/manual-run tests to assert the relocated action and unchanged saved-settings-only behavior.

- [x] Move configuration editing into `Backup settings`
  - [x] Place the `Destination` section inside the `Backup settings` panel without changing field names or prefixes.
  - [x] Place `Schedule and retention`, `Test S3 connection`, and `Save changes` inside the same panel while preserving existing POST actions.
  - [x] Extend settings-form tests to confirm save and S3 connection behavior still work after the layout move.

- [x] Add demo coverage for the tabbed backup settings UX
  - [x] Add `tests/e2e/backup-settings-tabs.spec.js` for the spec-defined superuser scenario.
  - [x] Capture the `backup-settings-tabs` screenshot checkpoint.
  - [x] Capture the `backup-settings-recent-backups-run-now` screenshot checkpoint.
  - [x] Capture the `backup-settings-backup-settings-tab` screenshot checkpoint.

# Deployment / Rollout

This is a UI-only rollout with no schema or scheduler changes expected.

Recommended rollout steps:

1. Deploy through the normal application release path.
2. Let the existing build/collectstatic flow handle any template or static asset updates.
3. Validate in a superuser session that `/backup-settings/` opens on `Recent backups`, the `Run backup now` action is in the recent-backups area, and `Backup settings` contains the configuration form.
4. Confirm the implementation PR/demo evidence uses the spec-declared Playwright command and includes the named screenshots.

# File-Level Changes

## Add

- `tests/e2e/backup-settings-tabs.spec.js` — issue-specific Playwright scenario for the tabbed backup settings UX

## Modify

- `invoices/templates/invoices/backup_settings.html` — replace the current first block with a two-tab layout and relocate the run-now action and settings form sections
- `invoices/tests/test_backups.py` — update render/manual-action assertions for the tabbed layout and unchanged POST behaviors

## Keep

- `invoices/views.py` — no backup route, permission, or execution-flow change is expected for this layout-only issue
- `invoices/urls.py` — existing backup routes remain unchanged
- `invoices/services/backups.py` — no backup service behavior change is expected
- `invoices/templates/invoices/backup_run_detail.html` — existing per-run detail behavior remains unchanged
- `invoices/static/invoices/css/design/components.css` — reuse the existing tab styling unless the backup screen exposes a small styling gap
- `scripts/e2e.sh` and `playwright.config.js` — reuse the existing Playwright runner/config for the spec-defined command

# Open Questions

None.
