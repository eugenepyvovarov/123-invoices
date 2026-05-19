# Overview

Add a small Playwright-based smoke test layer that exercises the highest-value browser flows in this Django app without slowing or destabilizing the existing fast test path. The first cut should cover login with OTP, company switching, invoice-list-to-drawer interaction, payment drawer submission, and Wise import modal behavior.

# Problem

Current automated coverage is strong at the Django/unit/integration layer but does not validate browser-only behavior end to end. That leaves risk around:

- the real login + OTP UI flow
- sidebar company switching behavior
- JavaScript-driven invoice drawer loading and save flow
- JavaScript-driven payment drawer flow
- Wise import modal upload behavior and inline error handling
- `fetch(...)`-based interactions that only exist in the browser

The repository also does not currently have any Node/Playwright tooling or a separate CI lane for browser tests.

# Proposed Outcome

Introduce a minimal Playwright smoke suite, backed by deterministic seeded data, with a dedicated local runner and separate CI workflow.

Recommended first-cut approach:

- Use Playwright’s standard Node toolchain in the repo root.
- Add a dedicated seed path for E2E data instead of creating data through UI setup flows.
- Add stable test selectors only where current markup is too brittle for reliable browser tests.
- Keep the suite intentionally small:
  - login and OTP verification to dashboard
  - company switch from the sidebar
  - invoice list status filter plus opening/editing an invoice drawer
  - payment drawer happy path
  - Wise import modal happy path plus one validation/error path
- Run E2E separately from `python manage.py test` and the current fast CI job.

# Constraints / Non-Goals

- Do not replace existing Django/unit/integration tests.
- Do not expand the first suite into broad CRUD coverage across the app.
- Do not require long click-through setup flows to prepare test state.
- Do not make Playwright part of the default fast validation command.
- Do not target multiple browsers in the initial rollout; one stable browser target is sufficient.
- Do not add visual regression, screenshot diffing, or exhaustive cross-device coverage in this issue.
- Prefer minimal template/JS changes for testability rather than UI redesign.

# Acceptance Criteria

## User Outcome

1. A smoke test can sign in through the real login screen, complete OTP verification, and land on the dashboard.
2. A smoke test can switch the active company from the sidebar and observe company-scoped UI/data update accordingly.
3. A smoke test can apply an invoice list filter, open an invoice edit drawer from the list UI, change a field, save, and observe the updated value after the drawer round trip.
4. A smoke test can open the payment drawer for an invoice, submit a valid payment, and observe the payment reflected after reload.
5. A smoke test can open the Wise import modal, upload a valid statement, and see a successful import summary.
6. A smoke test can trigger one Wise import validation/error case and see an inline failure message in the modal.

## Technical Behavior

1. Playwright tooling is installed and configured in the repository with a committed configuration file and runnable test suite.
2. E2E data setup is deterministic and created through code-level setup such as fixtures or a management command rather than multi-step UI preparation.
3. The OTP smoke path uses deterministic credentials and deterministic second-factor setup suitable for unattended execution.
4. Browser tests rely on stable selectors for fragile interactions where text-only or layout-based selectors would be brittle.
5. The invoice drawer smoke path exercises the existing async drawer endpoint and submit behavior, not a simplified alternate flow.
6. The payment drawer and Wise import smoke paths exercise the existing JavaScript `fetch(...)` flows against the running Django app.

## Operations / Deployment

1. A dedicated local command such as `scripts/e2e.sh` can prepare state and run the smoke suite end to end.
2. CI runs the Playwright suite in a separate workflow or job from the current Django/unit test job.
3. Failure in the Playwright lane is reported independently from the fast Django validation lane.
4. Required browser/runtime dependencies for CI are installed explicitly and reproducibly.

## Validation

1. The implementation documents how to run the E2E suite locally.
2. The initial smoke suite is small enough to remain practical for PR validation.
3. The seeded dataset includes the exact conditions needed for all first-cut scenarios, including multiple companies, an OTP-enabled user, invoice/payment fixtures, and Wise import fixture files.
4. The suite passes in CI using the committed seed/setup path and does not depend on manual local state.

# Implementation Plan

1. Add Playwright tooling at the repository root, including config, scripts, and an initial smoke test directory.
2. Add deterministic E2E data setup via a Django management command that creates:
   - a login user with known credentials
   - a confirmed OTP device with a known secret or equivalent deterministic verification path
   - two accessible companies for the same user
   - invoice/customer/project/payment fixtures for drawer flows
   - clean Wise import target state
3. Add fixture statement files for Wise import success and failure cases.
4. Add or tighten stable selectors for:
   - company switcher controls
   - invoice list quick-edit trigger
   - invoice drawer shell/content
   - payment drawer controls
   - Wise import modal controls and status
5. Add a small smoke suite organized by user journey, plus shared auth/seed helpers.
6. Add a separate CI workflow/job that installs Python + Node + Playwright browser dependencies, prepares the app, and runs the E2E suite.

# Task List

- [x] Add Playwright tooling and local runner
  - [x] Add root Playwright package metadata and lockfile for the browser test toolchain.
  - [x] Add `playwright.config` with a single-browser smoke configuration and base URL/server settings.
  - [x] Add `scripts/e2e.sh` to install prerequisites, prepare the test database, start Django, and run Playwright.
  - [x] Add a short local usage note for the E2E command.

- [x] Add deterministic E2E seed data and fixtures
  - [x] Add a Django management command that creates the E2E user, OTP setup, companies, and app data needed for all smoke scenarios.
  - [x] Add reusable fixture files for a valid Wise CSV/ZIP import case.
  - [x] Add a malformed or invalid Wise import fixture for the modal error-path test.
  - [x] Ensure the seed command can be rerun safely for local and CI execution.

- [x] Harden UI surfaces for reliable smoke coverage
  - [x] Add stable selectors to the login/OTP, sidebar company switcher, payment drawer, and Wise import modal surfaces.
  - [x] Add an explicit invoice-list trigger for opening the existing invoice drawer from the list page.
  - [x] Add any minimal selector/status markup needed so drawer and modal assertions do not rely on brittle presentation text alone.
  - [x] Verify selector changes do not alter normal user-facing behavior.

- [x] Add the initial Playwright smoke scenarios
  - [x] Add a login + OTP smoke test that reaches the dashboard.
  - [x] Add a company switch smoke test that verifies company-scoped content changes.
  - [x] Add an invoice list filter + invoice drawer edit smoke test.
  - [x] Add a payment drawer happy-path smoke test.
  - [x] Add Wise import happy-path and validation/error-path smoke tests.

- [x] Wire E2E into CI as a separate layer
  - [x] Add a dedicated GitHub Actions workflow or separate job for Playwright smoke tests.
  - [x] Install Node, Playwright browser dependencies, Python dependencies, and any OS packages required by the app/browser run.
  - [x] Run migrations, seed E2E data, execute the E2E command, and publish Playwright artifacts on failure if available.
  - [x] Keep the existing fast Django test workflow separate from the new browser lane.

# Deployment / Rollout

- No production migration is required for the feature itself unless the chosen seed/setup approach introduces a new optional management command only.
- Roll out as a separate CI lane first so browser-test failures do not get mixed into the existing fast validation command.
- Start with one browser target and a very small scenario set; expand only after this lane proves stable.
- If selector additions touch shared templates, validate that existing manual flows still behave the same locally.
- Store any CI-only environment defaults in workflow configuration rather than assuming developer-local state.

# File-Level Changes

## Add

- `package.json`
- `package-lock.json`
- `playwright.config.*`
- `scripts/e2e.sh`
- `tests/e2e/` or `e2e/` smoke spec files
- shared Playwright helpers/fixtures for auth and seed usage
- Wise import sample fixture files for success and error cases
- `invoices/management/commands/seed_e2e_smoke.py`
- dedicated GitHub Actions workflow for E2E if implemented as a separate workflow

## Modify

- `.github/workflows/django.yaml` only if needed to coordinate with a separate E2E job reference; otherwise leave the fast workflow isolated
- `accounts/templates/accounts/login.html`
- `accounts/templates/accounts/otp_verify.html`
- `invoices/templates/invoices/navbar.html`
- `invoices/templates/invoices/view_invoices.html`
- `invoices/templates/invoices/partials/invoice_drawer.html`
- `invoices/templates/invoices/partials/payment_drawer.html`
- `invoices/templates/invoices/partials/wise_import_modal.html`
- `invoices/static/invoices/js/invoice_drawer.js`
- `invoices/static/invoices/js/payment_drawer.js`
- `invoices/static/invoices/js/wise_import.js`
- any view/template code needed to expose an invoice-list drawer trigger reliably

## Keep

- Existing Django/unit/integration tests as the primary fast validation layer
- Existing invoice drawer, payment drawer, and Wise import backend endpoints as the browser-tested implementation targets
- Existing company-switch session behavior and active-company scoping model

# Open Questions

None.
