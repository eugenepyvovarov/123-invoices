# Overview

Fix the Playwright smoke workflow so CI can create and use its SQLite database reliably before migrations run. The recommended cut is to make the workflow prepare the database path explicitly and keep the smoke lane aligned with the existing local `scripts/e2e.sh` setup assumptions.

# Problem

The Playwright smoke action currently fails at `python manage.py migrate --noinput` with `sqlite3.OperationalError: unable to open database file`.

Repository context strongly suggests the failure is path preparation, not a broken migration:

- `app/settings.py` uses `DB_PATH` for SQLite.
- The Playwright workflow sets `DB_PATH: db/e2e.sqlite3`.
- `scripts/e2e.sh` creates the parent directory with `mkdir -p "$(dirname "${DB_PATH}")"` before migrations.
- The workflow runs migrations directly and does not create the `db/` directory first.

As a result, CI can fail before the smoke suite even starts, making the Playwright lane noisy and non-actionable.

# Proposed Outcome

Make the Playwright smoke workflow robust for fresh CI checkouts by ensuring the SQLite parent directory exists before any Django command touches the database, and reduce setup drift between CI and the local smoke runner.

Recommended approach:

- add an explicit database-path preparation step in the Playwright workflow before `migrate`
- keep the workflow using the same `DB_PATH` value across migrate, seed, and test execution
- where practical, rely on `scripts/e2e.sh` for shared behavior instead of duplicating fragile setup logic across workflow steps

# Constraints / Non-Goals

- Do not redesign the Playwright suite or expand smoke-test coverage.
- Do not change production database configuration.
- Do not add unrelated migration or model changes.
- Do not merge the Playwright lane into the fast Django test workflow.
- Do not assume the repository checkout contains a committed `db/` directory.

# Acceptance Criteria

## User Outcome

1. The Playwright smoke workflow completes database setup on a fresh CI checkout without failing on `unable to open database file`.
2. The smoke lane can proceed past migrations and reach seed and browser-test execution.

## Technical Behavior

1. The CI workflow creates or otherwise guarantees the parent directory for the configured SQLite `DB_PATH` before running Django migration commands.
2. The workflow uses one consistent smoke-test database path for migrate, seed, and Playwright execution.
3. The fix does not require committing the generated SQLite database file or relying on an already-present `db/` directory.
4. Local smoke execution through `scripts/e2e.sh` remains compatible with the CI configuration.

## Operations / Deployment

1. The fix is isolated to the Playwright smoke lane and does not change production deploy behavior.
2. The fast Django validation workflow remains separate from the browser smoke workflow.

## Validation

1. The updated workflow can be reasoned about from repository code and matches the existing local setup contract in `scripts/e2e.sh`.
2. A fresh CI run of the Playwright workflow no longer fails at the migration step due to SQLite path creation.
3. If setup logic is refactored, the workflow still publishes failure artifacts for downstream Playwright failures as it does today.

# Implementation Plan

1. Inspect the Playwright workflow and confirm all Django steps use the same `DB_PATH`.
2. Add an explicit pre-migration step to create the SQLite parent directory, or refactor the workflow to route setup through `scripts/e2e.sh` so directory creation is guaranteed by the shared script.
3. Keep migrate, seed, and smoke-test commands aligned on the same environment values.
4. Verify that the workflow still preserves current skip behavior and artifact upload behavior.

# Task List

- [x] Harden CI database setup
  - [x] Add a workflow step that creates the parent directory for `db/e2e.sqlite3` before `python manage.py migrate --noinput`.
  - [x] Verify the migrate and seed steps use the same `DB_PATH` value after the setup change.
  - [x] Verify the Playwright execution step uses that same `DB_PATH` value.

- [x] Reduce setup drift between CI and local smoke runs
  - [x] Compare the workflow setup sequence with `scripts/e2e.sh` and align any missing database-path preparation behavior.
  - [x] Prefer one shared setup path where feasible without collapsing current artifact handling or skip flags.
  - [x] Update any short usage note only if the chosen fix changes how smoke setup is invoked.

- [x] Validate workflow behavior
  - [x] Confirm the workflow no longer depends on a pre-existing committed `db/` directory.
  - [x] Confirm failure artifact upload behavior remains intact for actual Playwright failures.
  - [x] Confirm the fast Django CI workflow is unchanged.

# Deployment / Rollout

- This is a CI-only rollout with no production migration or runtime behavior change.
- After merging, validate the next Playwright workflow run specifically at the migration step and then at full smoke completion.
- If the first green run still exposes later smoke instability, treat that as follow-up work rather than expanding this fix.

# File-Level Changes

## Add

- None expected.

## Modify

- `.gitea/workflows/playwright.yml`
- `scripts/e2e.sh` only if setup responsibility is intentionally centralized there further

## Keep

- `app/settings.py`
- `.github/workflows/django.yaml`
- existing Playwright config and smoke tests unless a minimal alignment change is required

# Open Questions

None.
