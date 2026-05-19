# Overview

Add a superuser-only “Test S3 connection” action to the backup settings screen so admins can verify the configured S3-compatible destination without creating a backup artifact, uploading backup data, or recording a backup run.

# Problem

The current backup settings screen lets a superuser save S3 destination details, but it does not provide a safe way to confirm that the endpoint, bucket, and credentials are actually usable before the scheduled backup path runs.

That creates avoidable risk:
- misconfigured credentials are only discovered during a real backup attempt
- admins have no fast feedback loop in the UI
- using the existing backup execution path would create side effects the issue explicitly wants to avoid

# Proposed Outcome

Implement a second superuser-only submit action on the existing backup settings page:

- `Save changes` keeps the current persistence behavior.
- `Test S3 connection` validates the destination fields from the submitted form data and performs a non-destructive S3 connectivity check against the configured bucket.
- The test returns a concise UI message:
  - success confirms the destination is reachable and credentials work
  - failure reports a short actionable error
- The test path does not:
  - create a backup archive
  - upload any backup content
  - create a `BackupRun` row
  - trigger retention logic

Recommended implementation cut:
- handle the test as a second POST action on the existing `backup_settings` view rather than introducing a new screen
- add a dedicated service function for non-destructive destination validation, likely using the existing S3 client builder plus a bucket-level read/check operation such as `head_bucket`

# Constraints / Non-Goals

- The action must remain superuser-only, matching the existing backup settings authorization.
- The test must be non-destructive and must not write backup data remotely.
- Do not reuse `execute_backup` for this flow.
- Do not add a new backup run type unless the issue is explicitly re-scoped; this issue should avoid `BackupRun` persistence entirely.
- Do not expand scope to scheduler behavior, retention behavior, or backup artifact generation.
- Do not require non-superusers to see or interact with the action.

# Acceptance Criteria

## User Outcome

1. A superuser can use a visible action on the backup settings screen to test the current S3 destination configuration.
2. A successful test shows a concise confirmation message in the UI.
3. A failed test shows a concise actionable error message in the UI.
4. A non-superuser cannot access or trigger the test action.

## Technical Behavior

1. The test action validates the submitted backup destination fields needed for an S3 connection test before attempting the remote check.
2. The remote check verifies that the configured endpoint, bucket, and credentials are usable without generating a backup artifact or uploading backup content.
3. The test action does not create a `BackupRun` row.
4. The existing save-settings flow continues to work independently of the test flow.
5. The test action does not trigger retention logic or scheduled backup execution.

## Operations / Deployment

1. The feature requires no migration and no new operational process.
2. Deploying the feature does not change existing scheduled backup behavior.
3. The action remains inert unless a superuser explicitly triggers it from the backup settings UI.

## Validation

1. Automated tests cover superuser success and failure cases for the test action.
2. Automated tests cover non-superuser denial for the test action.
3. Automated tests confirm the test path does not create `BackupRun` records.
4. Automated tests confirm the test path does not call artifact creation, upload, or retention execution code.
5. Manual validation confirms the UI presents distinct save and test actions with clear feedback messages.

# Implementation Plan

1. Extend the existing backup settings POST handler to distinguish between save and test actions.
2. Reuse `BackupConfigurationForm` binding for the test action so validation is consistent with the settings screen.
3. Add a backup service helper that performs a non-destructive S3 bucket connectivity check using the submitted configuration.
4. Return short success or error messages through Django messages and re-render or redirect back to the settings page as appropriate.
5. Add focused tests for authorization, messaging, and no-side-effect guarantees.

# Task List

- [x] Add a non-destructive S3 test service
  - [x] Add a service function in `invoices/services/backups.py` that accepts a backup configuration instance and checks bucket access without uploading data.
  - [x] Normalize remote failures into concise user-facing error text suitable for the backup settings UI.
  - [x] Add service tests for a successful bucket check and a failed bucket check.

- [x] Add the backup settings UI action and controller flow
  - [x] Update the backup settings template to show a separate `Test S3 connection` submit action for superusers.
  - [x] Update the `backup_settings` view to branch between save and test actions on POST.
  - [x] Ensure the test action uses bound form data for validation and does not persist configuration changes unless the save action is used.
  - [x] Add view tests for superuser success, superuser failure, and non-superuser denial.

- [x] Add no-side-effect regression coverage
  - [x] Add a test proving the test action does not create a `BackupRun` row.
  - [x] Add a test proving the test action does not invoke backup artifact creation or backup upload behavior.
  - [x] Add a test proving the existing save action still persists settings and message behavior unchanged.

# Deployment / Rollout

No migration or rollout sequencing is required beyond normal application deploy.

Post-deploy verification:
1. Open the backup settings screen as a superuser.
2. Run the test action against a known-good bucket and confirm a success message.
3. Run the test action against an invalid bucket or credentials set and confirm a concise failure message.
4. Confirm no new entry appears in recent backup runs after either test.

# File-Level Changes

## Add

- None expected.

## Modify

- `invoices/views.py`
- `invoices/templates/invoices/backup_settings.html`
- `invoices/services/backups.py`
- `invoices/tests/test_backups.py`

## Keep

- `invoices/models.py` and existing backup migrations unchanged because the test action should not add persistence
- `invoices/urls.py` unchanged if the test remains a second POST action on the existing backup settings route
- existing backup execution, scheduler, and retention paths unchanged for this issue

# Open Questions

None.
