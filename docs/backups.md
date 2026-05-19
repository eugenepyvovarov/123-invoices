# Backups

## Overview

The app supports manual and scheduled backups for SQLite-based deployments.
Backups are configured from the superuser-only backup settings UI and executed
by application code. Scheduled backups require the `scheduler` service.

Automated backups are inactive until a superuser enables them.

## Runtime Requirements

Production should run both services from the same image:

- `web`: serves the app and handles manual backup actions.
- `scheduler`: runs `python manage.py run_backup_scheduler`.

Both services must share:

- the same `.env`;
- the same `/app/db` mount;
- the same `/app/media` mount.

This keeps backup configuration, backup history, uploaded media, and execution
locks consistent across manual and scheduled runs.

## Timezone

`BACKUP_SCHEDULING_TIMEZONE` controls how the daily run time is interpreted.
If it is blank, scheduled backups follow Django `TIME_ZONE`.

Set it explicitly in production when operators expect a local business-time
window:

```env
BACKUP_SCHEDULING_TIMEZONE=Europe/Madrid
```

Stored timestamps and object names remain UTC-based.

## Locking

The Compose runtime sets:

```env
BACKUP_EXECUTION_LOCK_PATH=/app/media/.locks/backup-execution.lock
```

The lock path must be on shared storage so a manual run and a scheduled run do
not execute at the same time.

## Object Keys

Uploaded backup objects use this layout:

```text
<optional-prefix>/YYYY/MM/DD/backup-<UTC timestamp>.zip
```

The backup history UI and retention pruning rely on this predictable layout.

## Operator Checks

After enabling backups:

1. Confirm the settings page shows the expected next run in
   `BACKUP_SCHEDULING_TIMEZONE`.
2. Run a manual backup and verify it appears as `manual`.
3. After the next scheduled window, verify the new run appears as `scheduled`.
4. If no scheduled run appears, inspect scheduler logs:

```bash
COMPOSE_PROJECT_NAME=03-invoices docker compose logs --no-color --tail 100 scheduler
```

For deployment-level container checks, use [Deployment](deployment.md).
