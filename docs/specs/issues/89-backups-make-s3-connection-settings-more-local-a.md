# Overview

Refine the superuser-only backup settings UX so S3 connection work happens in a local connection box, save/test actions complete in place without a full-page reload, and reviewer evidence includes both interaction media and full-page visual comparison for the updated form.

# Problem

The current `/backup-settings/` screen still treats two different concerns as one heavy form flow:

- S3 destination/connection fields
- backup schedule and retention fields

Today both `Test S3 connection` and `Save changes` post the whole form and reload the page. `Test S3 connection` also sits in the shared footer instead of beside the fields it validates. That makes the S3 check feel detached, drops the active tab back through postback handling, and makes narrow feedback feel heavier than necessary.

Because this issue changes visible form layout as well as behavior, reviewers also need explicit full-page comparison checkpoints instead of relying only on demo media.

# Proposed Outcome

Keep `/backup-settings/` and the existing superuser-only tabbed page, but tighten the `Backup settings` tab into two clearer surfaces:

- an S3 connection box for endpoint, bucket, region, prefix, and credentials
- a separate schedule/retention box for enablement, run time, and retention counts

Recommended cut:

- keep the existing `backup_settings` route as the integration point
- move `Test S3 connection` into the S3 connection box
- keep `Save changes` as the full-configuration persistence action
- progressively enhance the settings form so save and test submit via AJAX/fetch
- return action-scoped feedback in the settings tab instead of relying on a full-page refresh
- refresh visible saved-state UI, including the enabled/disabled badge, after successful AJAX saves
- reuse the existing Playwright backup-settings scenario explicitly for both demo evidence and reviewer-facing full-page capture

# Constraints / Non-Goals

- Keep `/backup-settings/`, the current permission model, and superuser-only access unchanged.
- Keep the `Recent backups` tab, recent run history, run-detail view, and `Run backup now` flow unchanged.
- Do not change backup execution logic, scheduler behavior, retention behavior, or `BackupRun` persistence semantics.
- Do not add a new visual regression framework; use the repository’s existing Playwright path and named checkpoints.
- Do not require live S3 reachability for reviewer evidence; deterministic validation and mocked server tests should still prove the UX.
- Assumption: preserve the current full-page POST behavior as a non-JavaScript fallback; the primary browser path becomes AJAX-driven.

# Acceptance Criteria

## User Outcome

1. A superuser opening the `Backup settings` tab sees a distinct S3 connection box separated from the schedule/retention box.
2. `Test S3 connection` is rendered inside the connection box instead of the shared footer.
3. Triggering `Test S3 connection` and `Save changes` in a JavaScript-enabled browser updates the screen in place without a full page reload and keeps the `Backup settings` tab active.
4. Test feedback appears within or directly adjacent to the connection box, while save feedback appears within the settings flow and edited values remain visible after the in-place response.

## Technical Behavior

1. The existing `/backup-settings/` route, form prefix, CSRF protection, and superuser gating remain in place.
2. The test action validates only the connection data required for the S3 reachability check, does not persist configuration changes, and does not create or execute a `BackupRun`.
3. The save action persists the full backup configuration and refreshes visible saved-state UI, including the enabled/disabled badge, without redirecting in the AJAX path.
4. Invalid AJAX submissions return server-rendered field errors and local feedback without dropping the user back to the default tab.
5. Existing non-superuser behavior and the `Recent backups` / `Run backup now` flows remain unchanged.

## Operations / Deployment

1. The change ships without migrations, scheduler changes, or runtime application environment additions. Managed review-workflow/config additions required for visual validation are allowed.
2. The normal build and collectstatic flow remains sufficient for any new static JS or template partials.
3. Current-head PR review evidence for full-page visual validation reports the spec-declared Playwright command, and the same command remains the declared final demo-media capture path after merge.

## Validation

1. Django tests cover the relocated button, connection-only test validation, AJAX save success, AJAX test success/error handling, no-persist test behavior, and unchanged superuser-only access.
2. The reused Playwright scenario verifies the no-reload settings interactions and captures the named demo checkpoints from this spec.
3. The same Playwright scenario captures the named full-page comparison checkpoints from this spec so reviewers can confirm the layout and feedback changes visually.

# Demo Media

### Scenario: backup-settings-tabs

#### Repo Command

`./scripts/e2e.sh tests/e2e/backup-settings-tabs.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow, promote that user to superuser through the existing Playwright setup path, open `/backup-settings/`, and switch to `Backup settings`.
2. Confirm the page shows a dedicated S3 connection box separate from the schedule/retention box, with `Test S3 connection` inside the connection box.
3. Clear one required connection field and trigger `Test S3 connection`.
4. Confirm the page does not navigate or fully reload, the `Backup settings` tab stays active, and connection-local validation or error feedback appears in place.
5. Restore a valid connection value, change a persisted field such as `Object prefix`, and trigger `Save changes`.
6. Confirm the page still does not navigate or fully reload, save feedback appears inside the settings flow, and the edited value plus visible saved-state UI remain updated after the in-place response.

#### Screenshot Checkpoints

- `backup-settings-connection-box`
- `backup-settings-test-validation`
- `backup-settings-save-success`

# Visual Validation

### Identifier

backup-settings-form-local-ajax

### Capture Command

`./scripts/e2e.sh tests/e2e/backup-settings-tabs.spec.js`

### Steps

1. Reach `/backup-settings/` through the same seeded superuser path used by the `backup-settings-tabs` scenario and activate the `Backup settings` tab.
2. Capture the initial full page with the new S3 connection and schedule/retention separation visible.
3. Trigger an in-place S3 test validation/error state and capture the resulting full page.
4. Restore valid input, submit `Save changes` in place, and capture the resulting full page with success feedback and refreshed saved-state UI.

### Full-Page Checkpoints

- `backup-settings-layout-full-page`
- `backup-settings-test-feedback-full-page`
- `backup-settings-save-feedback-full-page`

### Expected Comparisons

- Reviewers should see the S3 fields grouped into their own box, with `Test S3 connection` moved out of the shared footer and into that box.
- Reviewers should see connection feedback anchored to the active settings area instead of a page-level postback reset.
- Reviewers should see save success feedback and refreshed saved-state UI without the page returning to the default tab or reloading.

### Baseline SHA

`c38d6c1e24cabeaa25e3178a83e1551e5ca4da8f`


# Implementation Plan

1. Add an action-specific validation path in `invoices/forms.py` and `invoices/views.py` so the test action validates only the S3 fields needed for reachability while continuing to use the existing non-destructive destination test service.
2. Extract the settings-tab body into reusable server-rendered partials that separate the connection box from the schedule/retention box, relocate `Test S3 connection`, and render action-scoped feedback plus the header status badge.
3. Add a page-specific `invoices/static/invoices/js/backup_settings.js` controller that intercepts the settings form submit, detects which action button was clicked, sends the AJAX request with the repo’s existing request conventions, swaps returned fragments, and preserves the active settings tab.
4. Update `backup_settings` to return AJAX responses as JSON plus rendered HTML fragments for the settings panel and status badge while keeping the current full-page fallback behavior for non-JavaScript requests.
5. Extend Django and Playwright coverage around button placement, local feedback, no-reload behavior, full-page checkpoints, permission checks, and no-side-effect guarantees.

# Task List

- [x] Restructure the server-rendered backup settings UI
  - [x] Extract the settings-tab markup into reusable partials with separate S3 connection and schedule/retention boxes.
  - [x] Move `Test S3 connection` into the connection box and add local feedback regions for test and save results.
  - [x] Add a separately renderable status-badge fragment so AJAX saves can refresh the enabled/disabled state.

- [x] Add AJAX handling on the existing backup settings route
  - [x] Introduce a connection-only validation path for the test action while keeping full-form save validation unchanged.
  - [x] Return JSON plus rendered fragments for AJAX save/test success and invalid responses, while preserving the non-JavaScript fallback.
  - [x] Add `invoices/static/invoices/js/backup_settings.js` to intercept submits, send the clicked action, replace returned fragments, and keep the active tab stable.
  - [x] Extend Django tests for AJAX save success, AJAX test validation/error, no persistence on test, and unchanged superuser-only access.

- [x] Refresh the issue-bound Playwright evidence
  - [x] Explicitly update and reuse `tests/e2e/backup-settings-tabs.spec.js` for the no-reload settings interactions.
  - [x] Capture the demo checkpoints `backup-settings-connection-box`, `backup-settings-test-validation`, and `backup-settings-save-success`.
  - [x] Add full-page capture support and capture the visual-validation checkpoints `backup-settings-layout-full-page`, `backup-settings-test-feedback-full-page`, and `backup-settings-save-feedback-full-page`.

- [x] Validate the rollout path
  - [x] Run the targeted Django backup tests covering the changed form and view behavior.
  - [x] Verify the reused Playwright scenario remains the declared capture command for both PR visual validation and post-merge final demo media.
  - [x] Perform a superuser smoke check that `Recent backups` and `Run backup now` remain unchanged after deployment.

# Deployment / Rollout

This is a template/view/JS rollout with no schema or scheduler impact.

1. Deploy through the normal application release path.
2. Let the existing build and collectstatic flow publish any new static JS or template partial usage.
3. Post-deploy, validate as a superuser that `/backup-settings/` still loads, the `Backup settings` tab shows the relocated test action, an invalid test request returns local feedback without a reload, save returns local success without leaving the tab, and the `Recent backups` / `Run backup now` behavior is unchanged.
4. Keep the spec-declared Playwright command as the shared capture contract: PR visual validation should report that command now, and final demo media should keep using the same command after merge.

# File-Level Changes

## Add

- `invoices/static/invoices/js/backup_settings.js` — page-specific AJAX controller for the backup settings screen.
- `invoices/templates/invoices/partials/backup_settings_settings_panel.html` — server-rendered settings-panel fragment reused for initial render and AJAX refreshes.
- `invoices/templates/invoices/partials/backup_settings_status_badge.html` — header badge fragment so AJAX saves can refresh enabled/disabled state.

## Modify

- `invoices/templates/invoices/backup_settings.html` — include the new partials, load the page JS, and remove the old shared save/test footer layout.
- `invoices/views.py` — add AJAX response handling and action-scoped save/test branching on the existing route.
- `invoices/forms.py` — add or extend helpers so the test action validates only S3 connection inputs while save still uses the full configuration form.
- `invoices/tests/test_backups.py` — cover button placement, AJAX flows, local feedback, and permission/no-side-effect regressions.
- `tests/e2e/backup-settings-tabs.spec.js` — explicitly reused scenario updated for the in-place backup settings flow plus full-page review checkpoints.
- `tests/e2e/helpers/demo-evidence.js` — extend checkpoint capture so the reused scenario can emit the named full-page comparison screenshots.

## Keep

- `invoices/services/backups.py` — continue using the existing non-destructive destination test service instead of changing backup execution behavior.
- `invoices/urls.py` — the existing backup settings route remains the integration point.
- `invoices/models.py` and backup migrations — no schema changes are expected.
- `invoices/templates/invoices/backup_run_detail.html` and the recent-backups tab content — no changes are expected outside the settings interaction surface.
- `invoices/templates/invoices/partials/messages.html` — keep shared layout-level messages for non-AJAX flows such as manual backup execution.
- `scripts/e2e.sh` and `playwright.config.js` — reuse the current Playwright runner/config for the spec-defined command.

# Open Questions

None.
