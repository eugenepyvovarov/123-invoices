# Overview

Fix backup scheduling so automated daily backups run once per due window in the intended operator timezone, do not self-block on the shared lock file, and remain distinguishable from manual runs in persistence, logs, and UI.

# Problem

The current backup flow has three coupled defects:

1. The scheduler tick acquires a lock file and then calls `execute_backup()`, which attempts to acquire the same lock path again. This makes the scheduler appear to compete with itself and can skip valid scheduled work.
2. Scheduled due-window calculation uses Django local time while the app is configured with `TIME_ZONE = 'UTC'`, so `daily_run_time` is effectively interpreted as UTC instead of the intended business timezone.
3. `BackupRun` records do not persist trigger source, so any run in the current window can satisfy the scheduler check. A manual run can therefore suppress the scheduled run for that day.

# Proposed Outcome

1. Separate scheduler-tick coordination from backup-execution coordination so one scheduler loop cannot deadlock itself while real cross-process backup overlap protection remains in place.
2. Make scheduled due-window calculation use an explicit backup scheduling timezone, defaulting to Django `TIME_ZONE`, with production configured for the operator timezone (`Europe/Madrid` per the incident context).
3. Persist backup trigger source on `BackupRun` with at least `manual` and `scheduled` values.
4. Require the scheduler to treat only scheduled runs as satisfying the scheduled daily window.
5. Show trigger/source in backup history and backup run detail so operators can tell how each run was initiated.
6. Update backup settings copy so the configured daily time is clearly described in timezone terms.

# Constraints / Non-Goals

- Keep `USE_TZ = True`; timestamps should remain timezone-aware and stored consistently.
- Do not redesign backup retention, artifact creation, or S3 upload behavior beyond what is needed for trigger-aware run tracking.
- Do not add a per-user or per-issuer backup timezone UI in this issue.
- Do not merge manual and scheduled coordination into a new job system; keep the current management-command and service structure.
- Do not weaken real overlap protection between scheduler and web/manual execution across deployed containers.

# Acceptance Criteria

## User Outcome

1. A configured daily backup runs automatically once the scheduled local/operator time is reached.
2. A manual backup run on the same calendar day does not count as the scheduled run for that due window.
3. Backup history and backup run detail clearly identify whether a run was manual or scheduled.
4. Operators see timezone-aware schedule messaging that makes the configured run time unambiguous.

## Technical Behavior

1. Scheduler tick locking and backup execution locking use distinct lock semantics or paths, and the scheduler can successfully enter `execute_backup()` without self-blocking.
2. Real concurrent backup execution is still prevented across the deployed web and scheduler services.
3. Scheduled due-window calculation uses an explicit scheduling timezone rather than implicitly relying on UTC behavior.
4. `BackupRun` persists trigger source with at least `manual` and `scheduled` values, and existing rows receive a safe default.
5. The scheduler only considers scheduled runs when determining whether the current daily window has already been processed.
6. Manual backup entry points create `BackupRun` records with `manual` trigger source; scheduler-created runs use `scheduled`.

## Operations / Deployment

1. Production configuration supports the intended operator timezone for scheduled backups without requiring code edits after deploy.
2. The deployed split between `web` and `scheduler` services continues to work with shared overlap protection for actual backup execution.
3. Logs and UI provide enough information for operators to confirm whether the overnight run occurred and what trigger source produced each run.

## Validation

1. Automated tests cover the non-self-blocking scheduler path when the scheduler tick lock is held separately from the execution lock.
2. Automated tests cover manual and scheduled runs in the same due window and prove manual runs do not satisfy scheduled-run checks.
3. Automated tests cover due-window calculation in the configured scheduling timezone, including a non-UTC timezone case.
4. Automated tests cover manual and scheduled trigger assignment for the existing execution entry points.
5. Post-deploy validation confirms an automatically created scheduled run appears with `scheduled` trigger source in the deployed environment.

# Implementation Plan

1. Add explicit backup trigger metadata to `BackupRun` and thread it through all execution entry points.
2. Split scheduler tick locking from backup execution locking so scheduler coordination and backup overlap protection are independent.
3. Introduce a dedicated scheduling timezone helper/settings path used by both scheduler due-window calculation and backup settings display.
4. Update scheduler run selection logic to filter by trigger source when checking whether the current window has already been processed.
5. Update backup settings and run detail views/templates to expose trigger source and clarify timezone behavior.
6. Add regression coverage for lock behavior, timezone windows, and manual-vs-scheduled separation.
7. Document operational timezone behavior and any required environment configuration for production.

# Task List

- [x] Add trigger-aware backup run persistence
  - [x] Add `trigger_source` choices to `BackupRun` and create the migration with a safe default for existing rows.
  - [x] Update `execute_backup()` to require or default a trigger source and persist it on newly created runs.
  - [x] Update manual execution entry points (`run_backup_now`, `run_backup` command) to pass `manual`.
  - [x] Add tests covering trigger assignment for manual and scheduled execution paths.

- [x] Separate scheduler locking from execution locking
  - [x] Introduce a dedicated scheduler tick lock path/helper distinct from the backup execution lock path.
  - [x] Keep backup execution lock behavior as the shared overlap guard for real concurrent runs across processes.
  - [x] Add scheduler regression tests proving the scheduler no longer self-blocks while a real execution lock still blocks overlapping runs.

- [x] Make scheduled windows timezone-explicit and trigger-aware
  - [x] Add a scheduling timezone helper/setting that defaults to `TIME_ZONE` and is used for due-window calculations.
  - [x] Update scheduler duplicate-run detection to count only `scheduled` runs for the active due window.
  - [x] Update backup settings next-run calculation and display copy to reference the configured scheduling timezone.
  - [x] Add tests for non-UTC due-window calculation and for manual-plus-scheduled runs in the same daily window.

- [x] Expose operator-visible run source and rollout guidance
  - [x] Show trigger source in recent backup runs and backup run detail views.
  - [x] Add or update operator-facing documentation for scheduled backup timezone behavior and production configuration.
  - [x] Define a post-deploy validation step that confirms a scheduler-created run appears as `scheduled` after the configured local run time.

# Deployment / Rollout

- Requires a database migration for the new `BackupRun.trigger_source` field.
- Production should set the scheduling timezone explicitly to `Europe/Madrid` for the affected environment; keep UTC timestamp storage behavior unchanged.
- Deploy web and scheduler services together so the scheduler logic and execution lock behavior stay in sync.
- After deploy, verify:
  - backup settings page shows the expected next run time in the configured timezone,
  - a manual run is labeled `manual`,
  - the next automatic run creates a distinct `scheduled` record,
  - scheduler logs no longer emit false self-blocking messages during normal execution.

# File-Level Changes

## Modify

- `invoices/models.py` — add persisted backup trigger source to `BackupRun`.
- `invoices/services/backups.py` — accept/persist trigger source and keep execution locking as the shared concurrency guard.
- `invoices/management/commands/run_backup_scheduler.py` — split tick lock from execution lock, use explicit scheduling timezone, and filter due-window checks by scheduled trigger.
- `invoices/management/commands/run_backup.py` — pass manual trigger source.
- `invoices/views.py` — pass manual trigger source, update next-run calculation, and expose scheduling timezone/run source in context.
- `invoices/templates/invoices/backup_settings.html` — clarify timezone wording and show run source in history.
- `invoices/templates/invoices/backup_run_detail.html` — show run source in per-run summary.
- `invoices/tests/test_backups.py` — add regression coverage for lock separation, timezone handling, and manual-vs-scheduled behavior.
- `app/settings.py` — add explicit backup scheduling timezone setting/default.

## Add

- `invoices/migrations/*` — migration for `BackupRun.trigger_source`.
- Backup operations documentation location already used by the repo, if needed for timezone/deployment notes.

## Keep

- Existing retention classification and pruning flow.
- Existing S3 destination validation behavior.
- Existing deployed split between web and scheduler services.

# Open Questions

None.
