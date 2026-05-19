# Overview

Add an installation-level backup feature for Docker deployments that creates daily SQLite and media snapshots, uploads them to an S3-compatible object store, applies tiered retention, and exposes backup configuration plus recent run status in a dedicated superuser-only admin screen.

# Problem

The app currently has no backup subsystem, no scheduler process, no S3-compatible upload integration, and no installation-level operational settings area.

The issue also needs a sharper cut. The newest feedback confirms:
- SQLite-only support is acceptable for now.
- Backup configuration should live in a separate admin-facing frontend, not in company settings.
- Docker is the deployment target for scheduled execution.

Without that scope cut, implementation would mix installation operations with tenant/company settings and add unnecessary complexity around non-Docker deployments or non-SQLite databases.

# Proposed Outcome

Implement a first-cut backup system with these behaviors:

- A dedicated superuser-only backup admin screen allows configuration of:
  - S3-compatible endpoint, bucket, region, prefix, access key, and secret key
  - backup enablement
  - daily backup run time
  - retention counts for daily, weekly, and monthly preserved snapshots
- A backup job creates one compressed artifact containing:
  - the active SQLite database file
  - uploaded files under `MEDIA_ROOT`
- A separate scheduler process runs in Docker and triggers one backup when the configured daily run becomes due.
- Each run is recorded with status, timestamps, uploaded object key, size, and concise error details.
- Retention is enforced by keeping the configured number of daily, weekly, and monthly snapshots and pruning older remote objects outside those windows.

Recommended scope cut:
- Support daily automated backups only in this issue.
- Treat “regularity” as configured daily run time plus tiered retention, not arbitrary cron-style schedules.
- Exclude restore workflows.

# Constraints / Non-Goals

- SQLite is the only supported database backend in this issue.
- The scheduler is only required for the Docker/Compose deployment flow.
- Backup configuration is installation-wide and must not be stored on `Company` or `Issuer`.
- The backup UI must be separate from company settings and visible only to Django superusers.
- Do not add restore, download, or import-from-backup workflows.
- Do not add arbitrary cron expressions, multiple schedules, or per-backup-type schedules.
- Do not run the scheduler inside the web server process.
- Do not expand scope to Render or other non-Docker scheduling paths in this issue.

# Acceptance Criteria

## User Outcome

1. A Django superuser can open a dedicated backup admin screen and configure one S3-compatible destination plus backup retention settings.
2. A Django superuser can enable or disable automated backups and set the daily run time.
3. A Django superuser can view recent backup runs, including whether each run succeeded, failed, or is currently in progress.
4. Non-superusers cannot access the backup admin screen or backup history.

## Technical Behavior

1. The backup artifact includes the active SQLite database file and files from `MEDIA_ROOT`.
2. Backup execution is installation-scoped and does not depend on the active company in session.
3. Successful runs store timestamps, uploaded object key, artifact size, and retention classification data needed for pruning.
4. Failed runs store failure status and a concise error summary.
5. The scheduler runs as a separate Docker service and triggers at most one backup for a given due window.
6. Retention pruning preserves the configured daily, weekly, and monthly keep windows using the uploaded snapshots.
7. The upload key structure is deterministic enough to support history display and retention cleanup.

## Operations / Deployment

1. Docker/Compose configuration shows a separate scheduler service using the same image, environment, database mount, and media mount as the web container.
2. Deploying the feature without enabling backups does not change normal application behavior.
3. Rollout documentation identifies SQLite-only support and Docker-only scheduled execution for this first cut.

## Validation

1. Automated tests cover superuser-only access to backup configuration and history.
2. Automated tests cover backup settings validation and persistence.
3. Automated tests cover artifact creation for SQLite and media content and mock S3 upload behavior.
4. Automated tests cover run logging for both success and failure paths.
5. Automated tests cover retention selection and pruning behavior for daily, weekly, and monthly windows.
6. Automated tests cover scheduler due-check and overlap prevention behavior.
7. Manual validation confirms a Docker deployment can produce a successful uploaded backup and show the run in the UI.

# Implementation Plan

1. Add installation-level models for backup configuration and backup run history.
2. Add a superuser-only backup admin view, form, route, and template separate from company settings.
3. Add backup services to package SQLite plus media into a compressed artifact and upload it to an S3-compatible destination.
4. Add run logging and retention logic for daily, weekly, and monthly preservation windows.
5. Add management commands for one-off execution and long-running scheduler polling.
6. Extend Docker/Compose to run the scheduler as a separate service.
7. Add test coverage and deployment documentation for the SQLite + Docker first cut.

# Task List

- [x] Add installation-level backup persistence
  - [x] Add a backup configuration model for destination credentials, enablement, daily run time, and retention counts.
  - [x] Add a backup run model for status, timestamps, artifact metadata, and error summary.
  - [x] Add migrations for the backup models.
  - [x] Add model tests for validation and singleton-style configuration access.

- [x] Add superuser-only backup admin frontend
  - [x] Add a backup settings form for S3-compatible destination fields, enablement, daily run time, and retention values.
  - [x] Add a dedicated superuser-only backup settings/history view and route.
  - [x] Add a backup settings template with recent run history and next-run status.
  - [x] Add view and template tests for superuser access, non-superuser denial, and successful form submission.

- [x] Implement backup execution and retention services
  - [x] Add the S3-compatible client integration and dependency wiring.
  - [x] Add artifact creation logic that compresses the SQLite database file and `MEDIA_ROOT`.
  - [x] Add backup execution logic that writes success and failure run logs around upload attempts.
  - [x] Add retention classification and remote pruning logic for daily, weekly, and monthly windows.
  - [x] Add service tests for artifact creation, upload behavior, failure handling, and pruning outcomes.

- [x] Add Docker scheduler support
  - [x] Add a management command to run one backup on demand through the shared backup service.
  - [x] Add a long-running scheduler command that polls for due daily backups and skips when disabled or not due.
  - [x] Add overlap protection so concurrent scheduler ticks cannot start duplicate runs.
  - [x] Add command tests for due scheduling and overlap prevention.
  - [x] Update Docker/Compose and docs to run a separate scheduler service with shared mounts and environment.

# Deployment / Rollout

Rollout should be performed in this order:

1. Deploy the code, dependency, and database migration changes.
2. Start the separate scheduler service in Docker/Compose with the same `.env`, SQLite mount, and media mount as the web service.
3. Configure the backup destination and retention settings from the superuser-only backup admin screen.
4. Verify one successful scheduled or manual backup in a non-production bucket/prefix before relying on retention pruning in production.

Operational notes:
- Backups remain inert until explicitly enabled.
- The scheduler must share access to the SQLite file and uploaded media directory.
- Initial verification should confirm scheduler startup, successful upload, visible run history, and correct object placement under the configured prefix.

# File-Level Changes

## Add

- `invoices/services/backups.py`
- `invoices/management/commands/run_backup.py`
- `invoices/management/commands/run_backup_scheduler.py`
- `invoices/templates/invoices/backup_settings.html`
- `invoices/tests/test_backups.py` or split backup-focused test modules

## Modify

- `invoices/models.py`
- `invoices/forms.py`
- `invoices/views.py`
- `invoices/urls.py`
- `accounts/templates/accounts/user_settings.html`
- `invoices/admin.py`
- `requirements.txt`
- `docker-compose.yml`
- `README.md`
- `app/settings.py` if minimal backup defaults or staging-path settings are required

## Keep

- `invoices/templates/invoices/company_settings.html` as company-scoped issuer configuration
- existing `Company` and `Issuer` models as business-data settings, not backup settings
- the web server startup path as a separate process from backup scheduling

# Open Questions

None.
