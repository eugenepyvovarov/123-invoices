# Overview

Stabilize the existing automated test suite so the canonical validation commands return green on current `main`, then refactor the test layout into smaller, maintainable modules without changing production behavior or expanding into browser E2E coverage.

The recommended cut is:
- fix immediate suite blockers first
- update integration tests to reflect `LoginRequiredMiddleware` and active-company requirements
- replace large app-level catch-all test modules with feature-focused packages
- add missing auth/account coverage for login, OTP, and default-company behavior
- keep domain/service tests fast and isolated from server-rendered view tests where possible

# Problem

The current suite is failing for multiple independent reasons:

- `expenses/tests.py` contains a syntax error, which blocks discovery.
- Many request tests now receive login redirects because they were written before `LoginRequiredMiddleware` and active-company session handling were introduced.
- `tests/test_suite.py` manually manages `DiscoverRunner.setup_test_environment()` and breaks when run inside the broader suite.
- `accounts/tests.py` does not cover important current behavior around email login, OTP verification, and default-company selection.
- `invoices/tests.py` is a large mixed-purpose module, which makes failures harder to isolate and incremental maintenance harder.

As a result, the Docker-backed validation entrypoints (`scripts/ci.sh` and `scripts/coverage.sh`) are not reliable indicators of branch health.

# Proposed Outcome

Reshape the automated test suite into a stable layered structure:

- view/integration tests explicitly authenticate the client and set an active issuer/company through shared helpers or base classes
- auth/account coverage exists for the current login and user-settings flows, including OTP pending-state behavior and default-company updates
- `invoices` test coverage is split into feature-focused modules instead of one monolithic file
- chunk/smoke validation in `tests/test_suite.py` runs without nesting Django test-environment setup inside the main suite
- `scripts/ci.sh` and `scripts/coverage.sh` succeed without requiring special-case workarounds

This issue should improve confidence in existing behavior, not alter the product scope.

# Constraints / Non-Goals

- Do not add Playwright or other browser E2E coverage.
- Do not loosen or bypass `LoginRequiredMiddleware` in production code just to make older tests pass.
- Do not change user-facing auth or company-selection behavior unless a real bug is exposed while fixing tests.
- Do not introduce broad fixture magic that hides required setup or makes tests harder to read.
- Do not require schema changes for test-only restructuring.
- Keep domain/service tests separated from heavier view tests where that split is already practical.

# Acceptance Criteria

## User Outcome

1. The repository’s canonical automated validation commands complete successfully on a clean environment.
2. Existing protected server-rendered flows continue to require authentication, and automated coverage reflects that requirement instead of assuming anonymous access.
3. Auth/account behavior that users depend on today—email login, OTP verification flow, and default-company selection—has explicit regression coverage.

## Technical Behavior

1. The syntax/discovery blocker in the expenses test suite is removed.
2. Integration tests that exercise protected views use shared authenticated-company setup rather than duplicating ad hoc session manipulation across many classes.
3. `tests/test_suite.py` no longer manually nests Django test-environment setup in a way that conflicts with the full suite.
4. The large `invoices` catch-all test module is replaced with smaller feature-focused test modules grouped by behavior.
5. Domain/service tests remain runnable as focused units without depending on unrelated view setup.
6. Test refactoring does not weaken middleware enforcement, issuer scoping, or active-company behavior in production code.

## Operations / Deployment

1. The change ships without database migrations or data backfills.
2. Existing CI/review automation continues to use `scripts/ci.sh` and `scripts/coverage.sh` as the canonical entrypoints.
3. Rollout does not require feature flags or staged enablement.

## Validation

1. Automated coverage includes protected-view tests that verify authenticated access and correct active-company scoping.
2. Automated coverage includes account/auth tests for email login, OTP pending/verification behavior, and default-company updates.
3. Automated coverage includes focused tests for any shared helper/base-class behavior introduced for authenticated issuer setup.
4. Running `python manage.py test`, `scripts/ci.sh`, and `scripts/coverage.sh` succeeds after the refactor.

# Implementation Plan

1. Remove hard test-discovery/runtime blockers so the suite can execute far enough to reveal the remaining failures.
2. Introduce shared test helpers/base classes for authenticated users, issuer membership, and active-company session state, then update protected view tests to use them.
3. Split `accounts`, `expenses`, and especially `invoices` tests into package-based, feature-focused modules.
4. Add missing account/auth regression coverage around email login, OTP flow, and default-company behavior in `user_settings`.
5. Replace the nested `DiscoverRunner` pattern in `tests/test_suite.py` with an isolated validation approach that is safe under full-suite execution, then verify canonical validation commands.

# Task List

- [x] Remove immediate suite blockers
  - [x] Fix the syntax error in the expenses test module so Django test discovery can complete
  - [x] Update protected view tests that currently assume anonymous access to authenticate the client explicitly
  - [x] Standardize active-company session setup in the failing integration tests that depend on issuer-scoped data
  - [x] Replace the unsafe nested-runner pattern in `tests/test_suite.py` with a full-suite-safe smoke check

- [x] Introduce shared authenticated-company test support
  - [x] Add a reusable helper or base `TestCase` for creating a user linked to one or more issuers
  - [x] Add a reusable helper for logging in the test client and persisting `active_company_id`
  - [x] Refactor existing invoices/expenses integration tests to use the shared setup helpers
  - [x] Add focused tests for the helper/base behavior where it carries logic beyond simple object creation

- [x] Split app test modules into feature-focused packages
  - [x] Convert `accounts` tests from the placeholder module into a package with separate auth-flow and user-settings coverage
  - [x] Convert `expenses` tests into a package with view-focused modules after the blocker fix
  - [x] Replace the monolithic `invoices/tests.py` layout with smaller modules grouped by company, invoice, project, customer, and import/service behaviors
  - [x] Update any references in smoke/chunk tests so the new module paths are used consistently

- [x] Add missing auth/account regression coverage
  - [x] Add login-view tests for email-based authentication and OTP redirect behavior when a confirmed device exists
  - [x] Add OTP verification tests for success, invalid token handling, and missing pending-session handling
  - [x] Add `user_settings` tests for setting and clearing the default company with issuer access checks
  - [x] Add `user_settings` tests for TOTP enrollment/recovery-code flows that are currently untested

- [x] Restore canonical validation confidence
  - [x] Run the refactored suite through `python manage.py test` and fix any remaining deterministic failures exposed by the reorganization
  - [x] Verify `scripts/ci.sh` completes successfully against the restored suite
  - [x] Verify `scripts/coverage.sh` completes successfully and still reports coverage
  - [x] Update test-related docs only if command usage or module locations need clarification

# Deployment / Rollout

This is a test-stabilization and test-structure change, so rollout should follow the normal deploy path with no schema work.

Deployment considerations:
- no migration window is needed
- no feature flag is needed
- the main operational requirement is that managed automation continues to use the existing CI and coverage scripts unchanged unless a script-level defect is discovered

Post-merge validation should confirm:
- `python manage.py test` passes in the normal app environment
- `scripts/ci.sh` passes in the Docker-backed validation environment
- `scripts/coverage.sh` passes and produces a coverage report
- protected view tests still require explicit authenticated setup rather than silently regressing to anonymous access

# File-Level Changes

- Add `accounts/tests/` package with focused modules for login, OTP verification, and `user_settings` behavior
- Add `expenses/tests/` package with view-focused modules and shared setup usage
- Add `invoices/tests/` package with focused modules such as company, invoice, project, customer, and Wise import/service coverage
- Add shared test support modules under app test packages or a small common test helper area for authenticated issuer/company setup
- Modify `tests/test_suite.py` to use a full-suite-safe smoke/chunk validation approach
- Modify test references/import paths that currently point at class names inside `invoices.tests`
- Keep `scripts/ci.sh` and `scripts/coverage.sh` unless fixing the suite reveals an actual script defect rather than a test failure
- Keep production auth, middleware, and company-context code unless targeted test fixes expose a real application bug

# Open Questions

None.
