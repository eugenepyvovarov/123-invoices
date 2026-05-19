# Overview

Add a superuser-only way to inspect one backup run from backup history so operators can diagnose successful and failed runs from the app UI without needing server logs.

# Problem

The current backup settings screen shows only a small recent-runs table. It exposes basic fields inline, but it does not provide a per-run inspection workflow or enough persisted diagnostic context to explain where a run failed.

That leaves backup troubleshooting dependent on external server logs, which is exactly the gap this issue is trying to close.

# Proposed Outcome

Implement a dedicated per-run backup detail view, linked from backup history, that remains superuser-only and shows both summary metadata and structured run diagnostics.

Recommended scope cut:

- Add a superuser-only detail route for a single `BackupRun` from the existing backup history screen.
- Keep the history table concise, but add an explicit “View details” action for each run.
- Persist the minimum structured run-log data needed to support the detail view directly from `execute_backup`, rather than introducing broad general-purpose logging.

Recommended persisted detail shape:

- Continue using top-level `BackupRun` fields for core summary data already modeled today.
- Add one structured JSON field on `BackupRun` for per-run diagnostic detail, populated by backup execution code.
- Record a small ordered event log with stage-oriented entries such as:
  - run started
  - artifact created
  - upload started
  - upload finished
  - retention applied
  - failed at stage X
- Include failure metadata when relevant, at minimum:
  - failing stage
  - exception class
  - exception message / stored summary
  - any available structured context already known in code at that point

# Constraints / Non-Goals

- Keep backup history and per-run detail access restricted to Django superusers.
- Do not add server-log streaming, live log tailing, or external log aggregation.
- Do not add restore, re-run, download, or object-browser workflows in this issue.
- Do not expand backup scope beyond the existing installation-level backup system.
- Do not add verbose unstructured text blobs when a small structured event log is sufficient.
- Do not remove the existing summary fields from `BackupRun`; the new structured data should complement them.

# Acceptance Criteria

## User Outcome

1. A superuser can open a details view for an individual backup run from the backup history screen.
2. A successful run’s detail view shows useful per-run information including started time, finished time, object key, artifact size, status, and retention bucket.
3. A failed run’s detail view shows the stored error summary and any persisted structured diagnostic detail for the failure.
4. A non-superuser cannot access per-run backup details.

## Technical Behavior

1. The existing backup history view continues to list recent runs and adds a clear per-run detail action.
2. `BackupRun` persists the minimum structured per-run diagnostic data required to render the detail view without consulting server logs.
3. Backup execution records structured stage-level entries for both success and failure paths.
4. Failure diagnostics identify at least the failing execution stage and the captured exception type/message.
5. Existing summary fields on `BackupRun` remain the canonical source for status, timestamps, object key, artifact size, retention bucket, and concise error summary.

## Operations / Deployment

1. The change requires a database migration for the new structured diagnostic storage on `BackupRun`.
2. Existing backup scheduling and execution behavior remains unchanged apart from persisting additional per-run detail.
3. Deploying the change does not expose backup history or backup-run detail pages to non-superusers.

## Validation

1. Automated tests cover superuser access to the per-run detail view from backup history.
2. Automated tests cover non-superuser denial for the detail route.
3. Automated tests cover successful-run detail rendering with persisted summary and structured diagnostic data.
4. Automated tests cover failed-run detail rendering with stored error summary and structured failure diagnostics.
5. Automated tests cover backup execution persistence for the new structured run-log field in both success and failure paths.

# Implementation Plan

1. Extend `BackupRun` with a structured JSON-backed diagnostics field for per-run event entries and failure metadata.
2. Add lightweight helpers in the backup service to append stage-level events while `execute_backup` runs.
3. Update `execute_backup` to record structured events across artifact creation, upload, retention, and exception handling.
4. Add a superuser-only backup run detail view and route that loads one `BackupRun` and renders its summary plus structured diagnostics.
5. Update the backup history table to include a per-run detail action.
6. Add tests for service persistence, route authorization, and detail-page rendering.

# Task List

- [x] Add structured backup-run diagnostics storage
  - [x] Add a JSON field on `BackupRun` for structured run diagnostics and create the migration.
  - [x] Add a small model/helper default shape for ordered event entries and failure metadata.
  - [x] Add model-level tests for the new field’s default persisted structure if needed.

- [x] Persist per-run events during backup execution
  - [x] Add backup service helpers to append timestamped stage events to a run.
  - [x] Record success-path events for artifact creation, upload, and retention handling.
  - [x] Record failure-path diagnostics with failing stage, exception type, and message.
  - [x] Add service tests for structured diagnostics on both succeeded and failed runs.

- [x] Expose a superuser-only per-run detail UI
  - [x] Add a backup-run detail route and superuser-only view.
  - [x] Add a template for backup-run detail summary and structured diagnostic entries.
  - [x] Add a “View details” action from each row in backup history.
  - [x] Add view/template tests for superuser access, non-superuser denial, and rendered run details.

# Deployment / Rollout

- Apply the new migration before relying on the detail view in production.
- No scheduler or environment changes should be required.
- After deploy, validate with one successful run and one simulated failed run that the detail page renders persisted diagnostics without checking server logs.

# File-Level Changes

## Add

- `invoices/templates/invoices/backup_run_detail.html`
- `invoices/migrations/0059_*.py` for structured backup-run diagnostics storage

## Modify

- `invoices/models.py`
- `invoices/services/backups.py`
- `invoices/views.py`
- `invoices/urls.py`
- `invoices/templates/invoices/backup_settings.html`
- `invoices/tests/test_backups.py`

## Keep

- `invoices/management/commands/run_backup.py`
- `invoices/management/commands/run_backup_scheduler.py`
- existing superuser-only backup settings entry point and sidebar visibility rules

# Open Questions

None.
