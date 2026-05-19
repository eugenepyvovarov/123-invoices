# Overview

Add a superuser-only “Run backup now” action to the existing backup settings screen so an operator can trigger an immediate backup using the current saved configuration and then review the result in the same history UI already used for scheduled runs.

# Problem

The backup system currently supports scheduled execution and history display, but there is no admin UI action to run a backup on demand.

That creates two practical gaps:

- operators cannot verify a new backup configuration from the UI without waiting for the next scheduled window or using a management command
- the existing scheduler overlap protection does not yet define how a manual UI-triggered run should avoid duplicate concurrent execution alongside scheduled or other manual runs

The screen also already contains an editable settings form, so the manual action needs a clear boundary: it should run against the latest saved configuration, not unsaved form edits sitting in the page.

# Proposed Outcome

Implement a dedicated superuser-only POST action from the backup settings screen that:

- renders a visible “Run backup now” button on the existing backup settings page
- executes the same shared backup service used by scheduled runs
- uses the currently persisted `BackupConfiguration`
- records the run in `BackupRun` history through the existing backup execution flow
- shows a redirected success, failure, or “already running” message in the UI
- prevents duplicate concurrent runs across manual and scheduled entry points by using shared overlap protection around actual backup execution

Recommended cut:

- keep the action on the existing screen, but submit it to a dedicated POST endpoint rather than overloading the settings form POST
- keep the run synchronous for this issue so the operator gets immediate feedback and history refresh without introducing background job infrastructure
- do not add separate run-source tracking unless implementation reveals a real need

# Constraints / Non-Goals

- The action must remain superuser-only, matching the existing backup settings screen.
- The manual action must use the current saved backup configuration, not unsaved form values on the page.
- The implementation must reuse the same execution path as scheduled backups rather than creating a separate manual-only backup flow.
- The overlap guard must prevent concurrent duplicate runs across scheduler-triggered and UI-triggered execution.
- Do not add a background job queue, async worker system, or progress UI in this issue.
- Do not add restore, download, cancel, or retry workflows.
- Do not broaden the screen beyond the existing backup settings and recent history scope.
- Do not require a schema change unless implementation proves one is necessary for concurrency protection.

# Acceptance Criteria

## User Outcome

1. A superuser can trigger an immediate backup from the backup settings screen with a dedicated UI action.
2. After a manual trigger, the superuser receives clear feedback in the UI indicating success, failure, or that another backup is already in progress.
3. A manually triggered successful run appears in the recent backup history shown on the same screen.
4. A manually triggered failed run appears in the recent backup history with a concise error summary.
5. Non-superusers cannot see or invoke the manual backup action.

## Technical Behavior

1. The manual UI action invokes the same shared backup execution flow used by scheduled backups.
2. The manual UI action reads the currently persisted `BackupConfiguration` and does not depend on unsaved form edits from the page.
3. Backup history continues to be recorded through `BackupRun` with the existing success and failure fields populated consistently.
4. The system prevents duplicate concurrent runs across manual UI triggers and scheduled execution, or reports that a run is already in progress without starting another run.
5. Scheduled backups continue to behave as they do today aside from adopting any shared concurrency protection needed for cross-entry-point safety.

## Operations / Deployment

1. Deploying the feature does not require operators to change backup configuration or scheduler setup before using existing scheduled backups.
2. If no manual backup is triggered, normal application behavior remains unchanged.
3. Any new locking or overlap protection works in the deployed environment used by the scheduler and web process.

## Validation

1. Automated tests cover superuser visibility and access for the manual backup action.
2. Automated tests cover non-superuser denial for the manual backup action endpoint.
3. Automated tests cover successful manual execution feedback and history refresh behavior.
4. Automated tests cover failed manual execution feedback and the recorded `BackupRun.error_summary`.
5. Automated tests cover duplicate-run prevention when a backup is already in progress or the execution lock is already held.

# Implementation Plan

1. Add a dedicated superuser-only POST endpoint for “Run backup now” from the backup settings screen.
2. Update the backup settings template to render the new action separately from the settings save form.
3. Extract or extend shared backup execution locking so manual and scheduled paths use the same overlap protection.
4. Call the existing backup execution service from the new view using the persisted singleton configuration and redirect back with messages.
5. Expand backup tests to cover UI access, success and failure feedback, history updates, and overlap prevention.

# Task List

- [x] Add the manual backup trigger endpoint
  - [x] Add a dedicated superuser-only POST view for the run-now action that loads the saved backup configuration.
  - [x] Add a URL pattern for the run-now action separate from the settings form POST.
  - [x] Add redirect-with-message handling for success, failure, and already-running outcomes.

- [x] Update the backup settings UI
  - [x] Add a separate “Run backup now” form/button to the backup settings template.
  - [x] Keep the run-now action visually distinct from “Save changes” so operators do not confuse save vs run behavior.
  - [x] Add template/view tests for superuser visibility and non-superuser denial.

- [x] Share overlap protection across execution entry points
  - [x] Refactor existing scheduler-only locking into shared backup execution protection usable by both scheduler and UI.
  - [x] Update the scheduler path to use the shared protection without changing its due-window behavior.
  - [x] Add tests for duplicate-run prevention across manual and scheduled-style entry points.

- [x] Validate manual run outcomes in history and messaging
  - [x] Add tests for a successful manual run creating a visible history entry and success feedback.
  - [x] Add tests for a failed manual run preserving the recorded failure entry and concise error summary.
  - [x] Add tests confirming the manual action uses persisted configuration rather than unsaved page edits.

# Deployment / Rollout

No migration or operational rollout change is expected if the feature reuses existing models and scheduler setup.

Recommended rollout steps:

1. Deploy the code changes.
2. Verify the backup settings screen shows the manual action only for superusers.
3. Trigger one manual backup in a safe environment or non-production bucket/prefix to confirm success messaging and history recording.
4. Verify the scheduler still skips or reports overlap correctly if a manual run is already active.

Operational note:

- If shared locking is added, it must work across the deployed web process and scheduler process so duplicate runs are prevented in real usage, not just within one process.

# File-Level Changes

## Add

- None expected.

## Modify

- `invoices/views.py`
- `invoices/urls.py`
- `invoices/templates/invoices/backup_settings.html`
- `invoices/services/backups.py` or shared backup locking helpers in the existing backup command/service layer
- `invoices/management/commands/run_backup_scheduler.py`
- `invoices/tests/test_backups.py`

## Keep

- `invoices/models.py` and existing `BackupConfiguration` / `BackupRun` schema unless implementation proves a schema addition is necessary
- `invoices/management/commands/run_backup.py` as the existing non-UI immediate-run path
- existing backup history presentation on the backup settings screen as the primary review surface

# Open Questions

None.
